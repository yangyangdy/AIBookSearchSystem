"""健康检查接口"""
from fastapi import APIRouter
from loguru import logger

from src.api.models import HealthResponse
from src.core.milvus_client import MilvusClient
from src import __version__

router = APIRouter(prefix="/api/v1", tags=["health"])

# Milvus客户端（单例）
_milvus_client: MilvusClient = None


def get_milvus_client() -> MilvusClient:
    """获取Milvus客户端（单例）"""
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient()
    return _milvus_client


@router.get("/health", response_model=HealthResponse)
async def health():
    """
    健康检查
    
    Returns:
        系统状态
    """
    try:
        milvus_client = get_milvus_client()
        
        # 检查Milvus连接
        milvus_connected = True
        milvus_count = None
        
        try:
            milvus_count = milvus_client.count()
        except Exception as e:
            logger.warning(f"Milvus连接检查失败: {e}")
            milvus_connected = False
        
        return HealthResponse(
            status="healthy",
            version=__version__,
            milvus_connected=milvus_connected,
            milvus_count=milvus_count
        )
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return HealthResponse(
            status="unhealthy",
            version=__version__,
            milvus_connected=False,
            milvus_count=None
        )
