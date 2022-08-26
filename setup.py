#!/usr/bin/env python
from setuptools import find_namespace_packages, setup

setup(
    name="maua",
    version="0.4",
    description="Deep learning toolkit for image, video, and audio synthesis",
    author="Hans Brouwer",
    author_email="hans@wavefunk.xyz",
    url="https://github.com/maua-maua-maua/maua",
    packages=find_namespace_packages(
        include=["maua*"],
        exclude=[
            "maua.submodules.mmflow.tests*",
            "maua.submodules.mmflow.docs*",
            "maua.submodules.SwinIR.testsets*",
            "maua.submodules.VQGAN.data*",
            "maua.submodules.pycuda.bpl-subset*",
        ],
    ),
    package_data={
        "": ["*.yml", "*.yaml"],
        "maua.submodules.waifu2x*": ["*.zip", "*.7z"],
        "maua.submodules.stable_diffusion*": ["configs/*"],
    },
    include_package_data=True,
    install_requires=[
        "accelerate",
        "apex @ git+https://github.com/NVIDIA/apex",
        "auraloss",
        "av",
        "basicsr",
        "bitsandbytes",
        "cached_conv @ git+https://github.com/caillonantoine/cached_conv",
        "clean-fid",
        "click",
        "clip @ git+https://github.com/OpenAI/CLIP",
        "cupy-cuda116",
        "cython",
        "decord",
        "deep_translator",
        "dill",
        "easydict",
        "effortless_config",
        "einops",
        "ffmpeg_python",
        "filetype",
        "ftfy",
        "gdown",
        "gfpgan",
        "glumpy",
        "gputil",
        "h5py",
        "icetk",
        "imageio_ffmpeg",
        "localAttention @ git+https://github.com/Sleepychord/Image-Local-Attention.git",
        "joblib",
        "jsonmerge",
        "kornia",
        "librosa",
        "lpips",
        "madmom",
        "matplotlib",
        "medpy",
        "more_itertools",
        "ninja",
        "npy_append_array",
        "numba",
        "numpy",
        "nvidia-cuda-runtime-cu116",
        "nvidia-cuda-nvcc-cu116",
        "nvidia-cudnn-cu116",
        "omegaconf",
        "openunmix",
        "pandas",
        "prdc",
        "py7zr",
        "pyglet",
        "pyopengl",
        "pyspng",
        "pytorch-msssim",
        "pytorch_lightning",
        "pytorch_optimizer",
        "PyYaml",
        "realesrgan",
        "requests",
        "resampy",
        "resize_right",
        "scikit_learn",
        "scipy",
        "seaborn",
        "sentencepiece",
        "sklearn",
        "soundfile",
        "SwissArmyTransformer",
        "tensorboard",
        "tensorboardX",
        "termcolor",
        "timm",
        "torch",
        "torch_optimizer",
        "torchaudio",
        "torchcrepe",
        "torchcubicspline @ git+https://github.com/patrick-kidger/torchcubicspline.git",
        "torchdiffeq",
        "torchtyping",
        "torchvision",
        "tqdm",
        "transformers",
        "udls @ git+https://github.com/caillonantoine/UDLS",
        "unidecode",
        "wandb",
        "youtokentome",
    ],
    extras_require={
        "flow": ["mmflow", "mmcv-full"],
        "diffusion": [
            "basicsr",
            "clip",
            "cv2",
            "decord",
            "easydict",
            "einops",
            "ffmpeg",
            "gdown",
            "glide_text2im",
            "huggingface_hub",
            "kornia",
            "lpips",
            "matplotlib",
            "medpy",
            "npy_append_array",
            "numpy",
            "omegaconf",
            "PIL",
            "pytorch_msssim",
            "py7zr",
            "realesrgan",
            "requests",
            "resize_right",
            "scipy",
            "timm",
            "torch",
            "torchvision",
            "tqdm",
            "transformers",
        ],
    },
)
