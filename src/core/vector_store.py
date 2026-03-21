"""向量库工厂：按配置返回 Milvus 或 DashVector 客户端（进程内单例）"""
from __future__ import annotations

from typing import Union

from src.utils.config import get_settings
from src.core.milvus_client import MilvusClient
from src.core.dashvector_client import DashVectorClient

_store: Union[MilvusClient, DashVectorClient, None] = None


def get_vector_store() -> Union[MilvusClient, DashVectorClient]:
    global _store
    if _store is None:
        backend = get_settings().vector_backend
        if backend == "dashvector":
            _store = DashVectorClient()
        else:
            _store = MilvusClient()
    return _store