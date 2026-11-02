"""Ejecutable falso con la misma interfaz que realesrgan-ncnn-vulkan (para pruebas)."""

import argparse
import os
import sys
import time

from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-i")
    ap.add_argument("-o")
    ap.add_argument("-n", default="realesr-animevideov3")
    ap.add_argument("-s", type=int, default=4)
    ap.add_argument("-t", default="0")
    ap.add_argument("-f", default="png")
    ap.add_argument("-g", default="0")
    args = ap.parse_args()
    if log := os.environ.get("FAKE_ESRGAN_LOG"):
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"{args.n} {args.i}\n")
    if os.environ.get("FAKE_ESRGAN_FAIL"):
        print("vkCreateInstance failed -9", file=sys.stderr)
        return 255
    if delay := os.environ.get("FAKE_ESRGAN_SLEEP"):
        time.sleep(float(delay))
    with Image.open(args.i) as img:
        img.convert("RGB").resize((img.width * args.s, img.height * args.s), Image.BICUBIC).save(
            args.o, "PNG")
    print(f"fake: {args.n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
