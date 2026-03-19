"""批量处理脚本"""
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import logger as logger_module

logger_module.setup_logger("batch")

from loguru import logger
from src.batch.processor import BatchProcessor

# 命令行参数默认值（与 help 一致；进度文件不存在时由 ProgressTracker 首次自动创建）
DEFAULT_PROGRESS_FILE = "progress.json"
DEFAULT_OFFSET = None  # None：按进度文件中 last_processed_id 断点续跑
DEFAULT_MAX_RECORDS = None  # None：不限制条数，直到无数据


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="批量处理书籍封面数据",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "说明：若进度文件不存在，首次运行会在该路径自动创建初始 progress.json（含 offset=0、"
            "last_processed_id=null 等）。失败记录写入与进度文件同目录的 failed_records.jsonl。"
        ),
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=DEFAULT_OFFSET,
        metavar="ID",
        help="仅处理 MySQL id 大于该值的记录；不设则使用进度文件中的 last_processed_id",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=DEFAULT_MAX_RECORDS,
        metavar="N",
        help="最多处理多少条后停止；不设表示直到没有更多数据",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="重置进度（将进度文件写回初始状态后再跑）",
    )
    parser.add_argument(
        "--progress-file",
        type=str,
        default=DEFAULT_PROGRESS_FILE,
        metavar="PATH",
        help="进度 JSON 路径；不存在则自动创建",
    )
    
    args = parser.parse_args()
    
    logger.info("开始批量处理...")
    
    try:
        processor = BatchProcessor(progress_file=args.progress_file)
        
        processor.run(
            start_offset=args.offset,
            max_records=args.max_records,
            reset_progress=args.reset
        )
        
        processor.close()
        
        logger.info("批量处理完成")
        
    except KeyboardInterrupt:
        logger.warning("用户中断处理")
        sys.exit(1)
    except Exception as e:
        logger.error(f"批量处理失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
