"""失败记录持久化模块"""
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List
from loguru import logger


def _serializable_value(v: Any) -> Any:
    """将可能不可 JSON 序列化的值转为可序列化类型"""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "__float__") and type(v).__name__ == "Decimal":
        return float(v)
    return str(v)


def _serializable_record(record: Dict) -> Dict:
    """将 MySQL 记录转为可 JSON 序列化的字典"""
    if not record:
        return record
    return {k: _serializable_value(v) for k, v in record.items()}


class FailedRecordsStore:
    """失败记录持久化存储（JSONL 追加）"""

    def __init__(self, failed_records_file: str = "failed_records.jsonl"):
        """
        初始化失败记录存储

        Args:
            failed_records_file: JSONL 文件路径
        """
        self.failed_records_file = Path(failed_records_file)
        self.failed_records_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"失败记录存储初始化，文件: {self.failed_records_file}")

    def append(self, record: Dict, error: str) -> None:
        """
        追加一条失败记录

        Args:
            record: MySQL 记录（会做可序列化处理）
            error: 错误信息
        """
        line = {
            "record": _serializable_record(record),
            "error": error,
            "failed_at": datetime.utcnow().isoformat() + "Z",
        }
        try:
            with open(self.failed_records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"写入失败记录失败: {e}")

    def load_all(self) -> List[Dict]:
        """
        加载全部失败记录，供后续统一重试使用

        Returns:
            列表，每项为 {"record": ..., "error": ...}
        """
        if not self.failed_records_file.exists():
            return []
        result = []
        try:
            with open(self.failed_records_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    result.append(
                        {"record": item.get("record", {}), "error": item.get("error", "")}
                    )
        except Exception as e:
            logger.error(f"加载失败记录失败: {e}")
        return result
