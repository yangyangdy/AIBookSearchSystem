"""初始化Milvus Collection脚本"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.core.milvus_client import MilvusClient


def main():
    """主函数"""
    logger.info("开始初始化Milvus Collection...")
    
    try:
        milvus_client = MilvusClient()
        
        # 创建Collection（如果已存在则不重建）
        milvus_client.create_collection(force=False)
        
        # 获取记录数
        count = milvus_client.count()
        logger.info(f"Milvus Collection初始化完成，当前记录数: {count}")
        
        milvus_client.close()
        
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
