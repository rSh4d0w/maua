import math
import os
import sys
from functools import partial
from inspect import isfunction

import numpy as np
import torch
from einops import rearrange
from huggingface_hub import hf_hub_download
from omegaconf import OmegaConf
from torch import autocast, einsum

from ...prompt import ImagePrompt, TextPrompt
from ...utility import download
from .base import BaseDiffusionProcessor
from .latent import LatentDiffusion, load_model_from_config

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)) + "/../../submodules/k_diffusion")
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)) + "/../../submodules/stable_diffusion")
from ...submodules.k_diffusion import k_diffusion
from ...submodules.stable_diffusion.ldm.models.diffusion.ddim import DDIMSampler
from ...submodules.stable_diffusion.ldm.models.diffusion.plms import PLMSSampler


def default(val, d):
    if val is not None:
        return val
    return d() if isfunction(d) else d


def sliced_cross_attention(x, context=None, mask=None, self=None):
    h = self.heads

    q_in = self.to_q(x)
    context = default(context, x)
    k_in = self.to_k(context)
    v_in = self.to_v(context)
    del context, x

    q, k, v = map(lambda t: rearrange(t, "b n (h d) -> (b h) n d", h=h), (q_in, k_in, v_in))
    del q_in, k_in, v_in

    r1 = torch.zeros(q.shape[0], q.shape[1], v.shape[2], device=q.device)

    stats = torch.cuda.memory_stats(q.device)
    mem_active = stats["active_bytes.all.current"]
    mem_reserved = stats["reserved_bytes.all.current"]
    mem_free_cuda, _ = torch.cuda.mem_get_info(torch.cuda.current_device())
    mem_free_torch = mem_reserved - mem_active
    mem_free_total = mem_free_cuda + mem_free_torch

    gb = 1024**3
    tensor_size = q.shape[0] * q.shape[1] * k.shape[1] * q.element_size()
    modifier = 3 if q.element_size() == 2 else 2.5
    mem_required = tensor_size * modifier
    steps = 1

    if mem_required > mem_free_total:
        steps = 2 ** (math.ceil(math.log(mem_required / mem_free_total, 2)))

    if steps > 64:
        max_res = math.floor(math.sqrt(math.sqrt(mem_free_total / 2.5)) / 8) * 64
        raise RuntimeError(
            f"Not enough memory, use lower resolution (max approx. {max_res}x{max_res}). "
            f"Need: {mem_required/64/gb:0.1f}GB free, Have:{mem_free_total/gb:0.1f}GB free"
        )

    slice_size = q.shape[1] // steps if (q.shape[1] % steps) == 0 else q.shape[1]
    for i in range(0, q.shape[1], slice_size):
        end = i + slice_size
        s1 = einsum("b i d, b j d -> b i j", q[:, i:end], k) * self.scale

        s2 = s1.softmax(dim=-1, dtype=q.dtype)
        del s1

        r1[:, i:end] = einsum("b i j, b j d -> b i d", s2, v)
        del s2

    del q, k, v

    r2 = rearrange(r1, "(b h) n d -> b n (h d)", h=h)
    del r1

    return self.to_out(r2)


def use_sliced_attention(module):
    # don't use isinstance because CrossAttention could be from different implementations
    if module.__class__.__name__ == "CrossAttention":
        module.forward = partial(sliced_cross_attention, self=module)


def get_model(checkpoint):
    config = (
        os.path.abspath(os.path.dirname(__file__))
        + "/../../submodules/stable_diffusion/configs/stable-diffusion/v1-inference.yaml"
    )
    version = checkpoint.replace(".", "-")
    ckpt = f"modelzoo/stable-diffusion-v{version}.ckpt"
    if checkpoint in ["1.1", "1.2", "1.3"]:
        if not os.path.exists(ckpt):
            hf_hub_download(
                repo_id=f"CompVis/stable-diffusion-v-{version}-original",
                filename=f"sd-v{version}.ckpt",
                cache_dir="modelzoo/",
                force_filename=f"stable-diffusion-v{version}.ckpt",
                use_auth_token=True,
            )
    elif checkpoint == "1.4":
        if not os.path.exists(ckpt):
            download("https://bearsharktopus.b-cdn.net/drilbot_pics/sd-v1-4.ckpt", ckpt)
    elif checkpoint == "pinkney":
        sys.path.insert(
            0, os.path.abspath(os.path.dirname(__file__)) + "/../../submodules/stable_diffusion_image_conditioned"
        )
        config = (
            os.path.abspath(os.path.dirname(__file__))
            + "/../../submodules/stable_diffusion_image_conditioned/configs/stable-diffusion/sd-image-condition-finetune.yaml"
        )
        ckpt = f"modelzoo/stable-diffusion-image-conditioned.ckpt"
        if not os.path.exists(ckpt):
            download(
                "https://huggingface.co/lambdalabs/stable-diffusion-image-conditioned/resolve/main/sd-clip-vit-l14-img-embed_ema_only.ckpt",
                ckpt,
            )
    else:
        ckpt = checkpoint
    return load_model_from_config(OmegaConf.load(config), ckpt)


class StableConditioning(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, prompts):
        for prompt in prompts:
            if isinstance(prompt, TextPrompt):
                txt, _ = prompt()
                conditioning = self.model.get_learned_conditioning([txt])
                unconditional = self.model.get_learned_conditioning([""])
            elif type(prompt) == ImagePrompt:
                img, _ = prompt()
                conditioning = self.model.get_learned_conditioning(img)
                unconditional = torch.zeros_like(conditioning)
        return conditioning, unconditional


class StableDiffusion(LatentDiffusion):
    def __init__(
        self,
        grad_modules=[],
        cfg_scale=7.5,
        sampler="euler_ancestral",
        timesteps=100,
        model_checkpoint="1.4",
        ddim_eta=0,
        device="cuda" if torch.cuda.is_available() else "cpu",
        sliced_attention=True,
    ):
        super(BaseDiffusionProcessor, self).__init__()

        self.model = get_model(model_checkpoint)
        self.image_size = self.model.image_size * 8

        if sliced_attention:
            self.model.apply(use_sliced_attention)

        self.conditioning = StableConditioning(self.model)
        self.cfg_scale = cfg_scale

        if sampler == "plms":
            sampler = PLMSSampler(self.model)
            sampler.make_schedule(ddim_num_steps=timesteps, ddim_eta=ddim_eta, verbose=False)
            self.sample_fn = sampler.plms_sampling
            self.original_num_steps = sampler.ddpm_num_timesteps
        elif sampler == "ddim":
            sampler = DDIMSampler(self.model)
            sampler.make_schedule(ddim_num_steps=timesteps, ddim_eta=ddim_eta, verbose=False)
            self.sample_fn = sampler.ddim_sampling
            self.original_num_steps = sampler.ddpm_num_timesteps
        else:
            self.model_wrap = k_diffusion.external.CompVisDenoiser(self.model)
            self.sigmas = self.model_wrap.get_sigmas(timesteps)
            self.sample_fn = getattr(k_diffusion.sampling, f"sample_{sampler}")
            self.original_num_steps = len(self.model.alphas_cumprod)
            self.model_fn = partial(cfg_forward, model=self.model_wrap)

            self.grad_modules = [gm.to(device) for gm in grad_modules if gm.scale != 0]
            if len(self.grad_modules) > 0:

                def cond_fn(x, t, denoised, **kwargs):
                    img = self.model.differentiable_decode_first_stage(denoised)
                    img_grad = torch.zeros_like(img)
                    for grad_mod in self.grad_modules:
                        img_grad += grad_mod(img, t)
                    grad = -torch.autograd.grad(img, x, img_grad)[0]
                    return grad

                self.model_fn = conditioning_wrapper(self.model_fn, cond_fn)

        self.device = device
        self.model = self.model.to(device)
        self.timestep_map = np.linspace(0, self.original_num_steps, timesteps + 1).round().astype(int)

    @torch.no_grad()
    def forward(self, img, prompts, start_step, n_steps=None, verbose=True):
        if not hasattr(self, "sigmas"):
            return super().forward(img, prompts, start_step, n_steps, verbose)
            # LatentDiffusion class supports plms and ddim, below does not
            # TODO make all classes support k_diffusion samplers!

        if n_steps is None:
            n_steps = start_step + 1
        start_step = len(self.sigmas) - start_step - 2

        prompts = [p.to(img) for p in prompts]
        [gm.set_targets(prompts) for gm in self.grad_modules]
        cond, uncond = self.conditioning(prompts)

        with autocast(self.device), self.model.ema_scope():
            if start_step > 0:
                x = self.model.get_first_stage_encoding(self.model.encode_first_stage(img))
                x += torch.randn_like(x) * self.sigmas[start_step]
            else:
                x = torch.randn(
                    [img.shape[0], 4, img.shape[-2] // 8, img.shape[-1] // 8], device=img.device, dtype=img.dtype
                )
                x *= self.sigmas[0]

            shape = (x.shape[0], cond.shape[1], cond.shape[2])
            samples = self.sample_fn(
                self.model_fn,
                x,
                self.sigmas[start_step : start_step + n_steps + 1],
                extra_args={"cond": cond.expand(shape), "uncond": uncond.expand(shape), "cond_scale": self.cfg_scale},
                disable=not verbose,
            )
            samples_out = self.model.decode_first_stage(samples)

        return samples_out.float()


def cfg_forward(x, sigma, uncond, cond, cond_scale, model):
    x_in = torch.cat([x] * 2)
    sigma_in = torch.cat([sigma] * 2)
    cond_in = torch.cat([uncond, cond])
    uncond, cond = model(x_in, sigma_in, cond=cond_in).chunk(2)
    return uncond + (cond - uncond) * cond_scale


def conditioning_wrapper(model, cond_fn):
    def model_fn(x, sigma, **kwargs):
        with torch.enable_grad():
            x = x.detach().requires_grad_()
            denoised = model(x, sigma, **kwargs)
            cond_grad = cond_fn(x, sigma, denoised=denoised, **kwargs).detach()
            cond_denoised = denoised.detach() + cond_grad * k_diffusion.utils.append_dims(sigma**2, x.ndim)
        return cond_denoised

    return model_fn
