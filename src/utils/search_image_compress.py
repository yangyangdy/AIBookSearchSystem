"""检索接口专用：将查询图压至配置体积内（不影响批量入库）"""
from __future__ import annotations

import base64
import io
import re
import time

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


def _open_and_decode(raw: bytes, cfg) -> Image.Image:
    """
    打开并解码为 RGB 图。

    对 JPEG 优先使用 draft()，让解码器按接近 max_long_edge 的分辨率输出，
    避免把几千万像素完整展开到内存（这是大图压缩慢的主因之一）。
    """
    stream = io.BytesIO(raw)
    img = Image.open(stream)
    try:
        if img.format == "JPEG":
            img.draft("RGB", (cfg.max_long_edge, cfg.max_long_edge))
    except Exception:
        pass
    img.load()
    return img


def compress_search_image_bytes(raw: bytes, cfg) -> bytes:
    """
    将图片压为 JPEG，目标不超过 cfg.max_bytes。
    已小于 max_bytes 则原样返回（不解码）。

    算法概要：
    1) JPEG：draft 降采样解码；再 EXIF 转正、转 RGB。
    2) 按长边上限缩小（BILINEAR，优先速度）。
    3) 循环降低 JPEG quality，仍过大则缩小长边再试。
    4) save 不使用 optimize（减少 Huffman 二次扫描耗时）。
    """
    if not cfg.enabled:
        return raw
    if len(raw) <= cfg.max_bytes:
        return raw

    t0 = time.perf_counter()
    try:
        img = _open_and_decode(raw, cfg)
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

    # 超大原文件时略降起始质量，减少 JPEG 重编码次数
    q_start = cfg.jpeg_quality_start
    if len(raw) > 5_000_000:
        q_start = min(q_start, 80)
    quality_step = 8

    scale_side = cfg.max_long_edge
    best: bytes | None = None
    resize_filter = Image.Resampling.BILINEAR

    while scale_side >= cfg.min_long_edge:
        w, h = img.size
        if max(w, h) > scale_side:
            r = scale_side / max(w, h)
            im = img.resize(
                (max(1, int(w * r)), max(1, int(h * r))),
                resize_filter,
            )
        else:
            im = img

        q = q_start
        while q >= cfg.jpeg_quality_min:
            buf = io.BytesIO()
            im.save(
                buf,
                format="JPEG",
                quality=q,
                optimize=False,
                subsampling="4:2:0",
            )
            out = buf.getvalue()
            best = out
            if len(out) <= cfg.max_bytes:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                logger.debug(
                    f"检索图压缩完成: {len(raw)} -> {len(out)} bytes, "
                    f"long_edge<={scale_side}, JPEG q={q}, 耗时 {elapsed_ms:.1f} ms"
                )
                return out
            q -= quality_step

        if scale_side <= cfg.min_long_edge:
            break
        scale_side = max(cfg.min_long_edge, int(scale_side * 0.82))

    if best is not None:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning(
            f"检索图压缩未完全达标: 原始 {len(raw)} bytes，当前 {len(best)} bytes "
            f"(max_bytes={cfg.max_bytes})，耗时 {elapsed_ms:.1f} ms"
        )
        return best
    raise ValueError("压缩失败")
