"""OCR客户端模块"""
import time
from typing import Any, Optional

import dashscope
from loguru import logger

from src.utils.config import get_settings

# 与 DashScope OCR 推荐参数一致
_OCR_MIN_PIXELS = 32 * 32 * 3
_OCR_MAX_PIXELS = 32 * 32 * 8192


class OCRClient:
    """OCR 客户端（MultiModalConversation + 内置高精文字识别）"""

    def __init__(self):
        settings = get_settings()
        aliyun_config = settings.aliyun
        self._api_key = aliyun_config.api_key
        self._ocr_model = aliyun_config.ocr_model
        logger.info(f"OCR客户端初始化完成，模型: {self._ocr_model}")

    @staticmethod
    def _build_user_message(image: str) -> dict:
        """构建 user 消息：单条图像内容，含像素与转正参数。"""
        return {
            "role": "user",
            "content": [
                {
                    "image": image,
                    "min_pixels": _OCR_MIN_PIXELS,
                    "max_pixels": _OCR_MAX_PIXELS,
                    "enable_rotate": True,
                }
            ],
        }

    @staticmethod
    def _parse_ocr_text(response: Any) -> Optional[str]:
        """从 output.choices[0].message.content[0].text 取识别文本。"""
        try:
            out = response.output
            if isinstance(out, dict):
                choices = out.get("choices") or []
                msg = (choices[0].get("message") if choices else None) or {}
                content = msg.get("content") or []
                first = content[0] if content else {}
                text = first.get("text") if isinstance(first, dict) else getattr(
                    first, "text", None
                )
            else:
                choices = getattr(out, "choices", None) or []
                if not choices:
                    return None
                msg = getattr(choices[0], "message", None)
                if msg is None:
                    return None
                content = getattr(msg, "content", None) or []
                if not content:
                    return None
                first = content[0]
                text = (
                    first.get("text")
                    if isinstance(first, dict)
                    else getattr(first, "text", None)
                )
            return text if text is not None else None
        except (IndexError, KeyError, AttributeError, TypeError) as e:
            logger.error(f"解析 OCR 响应失败: {e}, output={getattr(response, 'output', None)}")
            return None

    def _call_ocr(self, messages: list) -> Optional[str]:
        t0 = time.perf_counter()
        try:
            response = dashscope.MultiModalConversation.call(
                api_key=self._api_key,
                model=self._ocr_model,
                messages=messages,
                ocr_options={"task": "text_recognition"},
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                f"OCR(MultiModalConversation) 请求耗时: {elapsed_ms:.2f} ms, model={self._ocr_model}"
            )
            logger.error(f"OCR 调用异常: {e}")
            return None
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            f"OCR(MultiModalConversation) 请求耗时: {elapsed_ms:.2f} ms, model={self._ocr_model}"
        )

        if response.status_code != 200:
            msg = getattr(response, "message", "") or str(response)
            logger.error(f"OCR 失败，状态码: {response.status_code}, 错误: {msg}")
            return None

        text = self._parse_ocr_text(response)
        if text is None:
            logger.error("OCR 响应中未找到文本内容")
            return None
        logger.debug(f"OCR 成功，文字长度: {len(text)}")
        return text

    def extract_text(self, image_url: str) -> Optional[str]:
        """
        从图片 URL 提取文字（高精识别 text_recognition）。
        """
        messages = [self._build_user_message(image_url)]
        return self._call_ocr(messages)

    def extract_text_from_base64(self, image_base64: str) -> Optional[str]:
        """
        从 Base64 提取文字。
        """
        raw = image_base64.strip()
        if not raw.startswith("data:"):
            raw = f"data:image/jpeg;base64,{raw}"
        messages = [self._build_user_message(raw)]
        return self._call_ocr(messages)
