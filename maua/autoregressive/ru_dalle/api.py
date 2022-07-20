import argparse
import base64
from io import BytesIO

import requests
from PIL import Image
from transformers import AutoModelForSeq2SeqLM, MarianTokenizer


def request_kandinsky(input_text, request_url, top_k=1500, top_p=0.99, images_num=4, rerank_top=4, verbose=False):
    mname = "Helsinki-NLP/opus-mt-en-ru"
    translate_tokenizer = MarianTokenizer.from_pretrained(mname)
    translator = AutoModelForSeq2SeqLM.from_pretrained(mname)

    input_ids = translate_tokenizer.encode(input_text, return_tensors="pt")
    outputs = translator.generate(input_ids)
    text = translate_tokenizer.decode(outputs[0], skip_special_tokens=True)

    if verbose:
        print(f"translated:\n{input_text}\n{text}\n")

    response = requests.post(
        request_url,
        json={
            "instances": [
                {
                    "text": text,
                    "top_k": top_k,
                    "top_p": top_p,
                    "images_num": images_num,
                    "rerank_top": rerank_top,
                    "hi_res": True,
                }
            ]
        },
    )

    if verbose:
        print(f"received response:\n{response}\n")

    for imgtext in response.json()["images"]:
        msg = base64.b64decode(imgtext.encode("ascii"))
        img = Image.open(BytesIO(msg))
        yield img


def main(args):
    for i, img in enumerate(
        request_kandinsky(
            args.input_text, args.request_url, args.top_k, args.top_p, args.images_num, args.rerank_top, args.verbose
        )
    ):
        img.save(f"{args.out_dir}/{args.input_text.replace(' ', '_')}_rudalle_kandinsky_{i}.png")
