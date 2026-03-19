"""进度追踪模块"""
import json
from pathlib import Path
from typing import Optional
from loguru import logger

_INITIAL_PROGRESS = {
    "offset": 0,
    "last_processed_id": None,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "failed_records": [],
}


class ProgressTracker:
    """进度追踪器"""
    
    def __init__(self, progress_file: str = "progress.json"):
        """
        初始化进度追踪器
        
        Args:
            progress_file: 进度文件路径
        """
        self.progress_file = Path(progress_file)
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.progress_file.exists():
            self.save(dict(_INITIAL_PROGRESS))
            logger.info(f"进度文件不存在，已创建: {self.progress_file}")
        logger.info(f"进度追踪器初始化，文件: {self.progress_file}")
    
    def load(self) -> dict:
        """
        加载进度
        
        Returns:
            进度字典
        """
        if not self.progress_file.exists():
            return dict(_INITIAL_PROGRESS)
        
        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "last_processed_id" not in data:
                    data["last_processed_id"] = None
                return data
        except Exception as e:
            logger.error(f"加载进度失败: {e}")
            return dict(_INITIAL_PROGRESS)
    
    def save(self, progress: dict):
        """
        保存进度
        
        Args:
            progress: 进度字典
        """
        try:
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
            logger.debug(f"进度已保存: offset={progress.get('offset')}, processed={progress.get('processed')}")
        except Exception as e:
            logger.error(f"保存进度失败: {e}")
    
    def update(
        self,
        offset: int,
        processed: int,
        success: int,
        failed: int,
        failed_records: Optional[list] = None,
        last_processed_id: Optional[int] = None
    ):
        """
        更新进度
        
        Args:
            offset: 当前偏移量（下次从第 offset 条开始取）
            processed: 已处理数量
            success: 成功数量
            failed: 失败数量
            failed_records: 失败记录列表
            last_processed_id: 本批已处理到的最后一条 MySQL 记录 id（ORDER BY id 时，下次可从该 id 之后继续）
        """
        progress = {
            "offset": offset,
            "last_processed_id": last_processed_id,
            "processed": processed,
            "success": success,
            "failed": failed,
            "failed_records": failed_records or []
        }
        self.save(progress)
    
    def get_offset(self) -> int:
        """获取当前偏移量"""
        progress = self.load()
        return progress.get("offset", 0)

    def get_last_processed_id(self) -> Optional[int]:
        """获取已处理到的最后一条记录 id"""
        progress = self.load()
        return progress.get("last_processed_id")
    
    def reset(self):
        """重置进度"""
        self.update(0, 0, 0, 0, [], last_processed_id=None)
