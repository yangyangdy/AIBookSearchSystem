"""健康检查接口"""
from fastapi import APIRouter
from loguru import logger

from src.api.models import HealthResponse
from src.core.vector_store import get_vector_store
from src.utils.config import get_settings
from src import __version__

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health():
    """
    健康检查
    
    Returns:
        系统状态
    """
    settings = get_settings()
    backend = settings.vector_backend
    try:
        vector_store = get_vector_store()
        milvus_connected = True
        milvus_count = None
        
        try:
            milvus_count = vector_store.count()
        except Exception as e:
            logger.warning(f"向量库连接检查失败: {e}")
            milvus_connected = False
        
        return HealthResponse(
            status="healthy",
            version=__version__,
            vector_backend=backend,
            milvus_connected=milvus_connected,
            milvus_count=milvus_count,
        )
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return HealthResponse(
            status="unhealthy",
            version=__version__,
            vector_backend=backend,
            milvus_connected=False,
            milvus_count=None,
        )
