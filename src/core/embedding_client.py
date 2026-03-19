"""向量化客户端模块"""
import time
from typing import Optional, List

import dashscope
from loguru import logger

from src.utils.config import get_settings


class EmbeddingClient:
    """向量化客户端（基于 DashScope MultiModalEmbedding）"""

    def __init__(self):
        """初始化向量化客户端"""
        settings = get_settings()
        aliyun_config = settings.aliyun
        # api_key 仅来自配置（如 config.yaml / 环境变量 ALIYUN_API_KEY），勿在代码中写死
        self._api_key = aliyun_config.api_key
        self.model = aliyun_config.embedding_model
        # 与 qwen3-vl-embedding 等模型一致，需与 Milvus collection 维度一致
        self.dimension = aliyun_config.embedding_dimension

        logger.info(
            f"向量化客户端初始化完成，模型: {self.model}, dimension: {self.dimension}"
        )

    def _call_multimodal_embedding(self, image_input: str, is_url: bool) -> Optional[List[float]]:
        """
        调用 MultiModalEmbedding，解析 output.embeddings[0].embedding
        """
        if is_url:
            input_payload = [{"image": image_input}]
        else:
            # Base64：无 data URI 前缀时补全，便于接口识别
            img = image_input.strip()
            if not img.startswith("data:"):
                img = f"data:image/jpeg;base64,{img}"
            input_payload = [{"image": img}]

        t0 = time.perf_counter()
        try:
            response = dashscope.MultiModalEmbedding.call(
                api_key=self._api_key,
                model=self.model,
                dimension=self.dimension,
                input=input_payload,
            )
        except Exception as call_err:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                f"MultiModalEmbedding 请求耗时: {elapsed_ms:.2f} ms, model={self.model}"
            )
            logger.error(f"MultiModalEmbedding 调用异常: {call_err}")
            return None
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            f"MultiModalEmbedding 请求耗时: {elapsed_ms:.2f} ms, model={self.model}"
        )

        if response.status_code != 200:
            msg = getattr(response, "message", "") or str(response)
            logger.error(
                f"向量化失败，状态码: {response.status_code}, 错误: {msg}"
            )
            return None

        try:
            out = response.output
            embeddings = out.get("embeddings") if isinstance(out, dict) else getattr(
                out, "embeddings", None
            )
            if not embeddings:
                logger.error(f"向量化响应无 embeddings: {out}")
                return None
            first = embeddings[0]
            embedding = (
                first.get("embedding")
                if isinstance(first, dict)
                else getattr(first, "embedding", None)
            )
            if not embedding:
                logger.error(f"向量化响应无 embedding 字段: {first}")
                return None
            logger.debug(f"向量化成功，维度: {len(embedding)}")
            return list(embedding)
        except Exception as e:
            logger.error(f"解析向量化响应失败: {e}, output={getattr(response, 'output', None)}")
            return None

    def get_embedding(self, image_url: str) -> Optional[List[float]]:
        """
        获取图片向量（图片 URL）

        Args:
            image_url: 图片 URL

        Returns:
            向量列表，失败返回 None
        """
        try:
            return self._call_multimodal_embedding(image_url, is_url=True)
        except Exception as e:
            logger.error(f"向量化异常: {e}")
            return None

    def get_embedding_from_base64(self, image_base64: str) -> Optional[List[float]]:
        """
        从 Base64 获取图片向量

        Args:
            image_base64: Base64 编码的图片（可为纯 base64 或 data:image/...;base64,...）

        Returns:
            向量列表，失败返回 None
        """
        try:
            return self._call_multimodal_embedding(image_base64, is_url=False)
        except Exception as e:
            logger.error(f"向量化异常: {e}")
            return None
