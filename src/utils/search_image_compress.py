"""检索接口专用：将查询图压至配置体积内（不影响批量入库）"""
from __future__ import annotations

import base64
import io
import re

from PIL import Image, ImageOps
from loguru import logger


def decode_base64_to_bytes(b64_or_data_uri: str) -> bytes:
    """解析纯 base64 或 data:image/...;base64,..."""
    s = (b64_or_data_uri or "").strip()
    if not s:
        raise ValueError("Base64 为空")
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    s = re.sub(r"\s+", "", s)
    try:
        return base64.standard_b64decode(s, validate=True)
    except Exception:
        return base64.standard_b64decode(s)


def compress_search_image_bytes(raw: bytes, cfg) -> bytes:
    """
    将图片压为 JPEG，目标不超过 cfg.max_bytes。
    已小于 max_bytes 则原样返回（不解码，避免无谓 CPU）。
    """
    if not cfg.enabled:
        return raw
    if len(raw) <= cfg.max_bytes:
        return raw

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as e:
        raise ValueError(f"无法解析图片: {e}") from e

    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        img = bg
    elif img.mode == "P":
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if "A" in img.getbands() else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    scale_side = cfg.max_long_edge
    best: bytes | None = None

    while scale_side >= cfg.min_long_edge:
        im = img
        w, h = im.size
        if max(w, h) > scale_side:
            r = scale_side / max(w, h)
            im = im.resize((max(1, int(w * r)), max(1, int(h * r))), Image.Resampling.LANCZOS)

        q = cfg.jpeg_quality_start
        while q >= cfg.jpeg_quality_min:
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=q, optimize=True)
            out = buf.getvalue()
            best = out
            if len(out) <= cfg.max_bytes:
                logger.info(
                    f"检索图压缩: {len(raw)} -> {len(out)} bytes, "
                    f"long_edge<={scale_side}, JPEG q={q}"
                )
                return out
            q -= 6

        if scale_side <= cfg.min_long_edge:
            break
        scale_side = max(cfg.min_long_edge, int(scale_side * 0.82))

    if best is not None:
        logger.warning(
            f"检索图压缩未完全达标: 原始 {len(raw)} bytes，当前 {len(best)} bytes "
            f"(max_bytes={cfg.max_bytes})，已尽力缩小"
        )
        return best
    raise ValueError("压缩失败")
