"""初始化 DashVector Collection 脚本"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.core.dashvector_client import DashVectorClient


def main():
    logger.info("开始初始化 DashVector Collection...")

    try:
        client = DashVectorClient()
        client.create_collection(force=False)
        count = client.count()
        logger.info(f"DashVector Collection 初始化完成，当前记录数: {count}")
        client.close()
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()