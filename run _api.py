"""启动API服务"""
import uvicorn
from src.utils.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    api_config = settings.api
    
    uvicorn.run(
        "src.api.main:app",
        host=api_config.host,
        port=api_config.port,
        reload=True  # 开发模式，生产环境设为False
    )