"""批量处理主流程"""
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

from src.core.mysql_client import MySQLClient
from src.core.vector_store import get_vector_store
from src.core.image_processor import ImageProcessor
from src.core.embedding_client import EmbeddingClient
from src.core.ocr_client import OCRClient
from src.batch.progress import ProgressTracker
from src.batch.failed_store import FailedRecordsStore
from src.utils.config import get_settings


class BatchProcessor:
    """批量处理器"""
    
    def __init__(self, progress_file: str = "progress.json"):
        """
        初始化批量处理器
        
        Args:
            progress_file: 进度文件路径
        """
        # 初始化各个客户端
        self.mysql_client = MySQLClient()
        self.vector_store = get_vector_store()
        self.image_processor = ImageProcessor()
        self.embedding_client = EmbeddingClient()
        self.ocr_client = OCRClient()
        self.progress_tracker = ProgressTracker(progress_file)
        # 失败记录持久化：与 progress 同目录的 failed_records.jsonl
        failed_records_file = Path(progress_file).parent / "failed_records.jsonl"
        self.failed_store = FailedRecordsStore(str(failed_records_file))

        # 获取配置
        settings = get_settings()
        self.batch_size = settings.processing.batch_size
        self.max_workers = settings.processing.max_workers
        
        logger.info("批量处理器初始化完成")
    
    def process_single_record(self, record: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        处理单条记录
        
        Args:
            record: MySQL记录
        
        Returns:
            (处理结果字典, 错误信息)
        """
        mysql_id = record["id"]
        sku = record.get("sku", "")
        isbn = record.get("isbn", "")
        author = record.get("author", "")
        cover_link = record["cover_link"]
        
        try:
            # 1. 处理图片（下载、验证、计算哈希）
            cover_hash, error = self.image_processor.process_image(cover_link)
            if cover_hash is None:
                return None, f"图片处理失败: {error}"
            
            # 2. 并行处理：向量化 + OCR
            embedding = None
            ocr_text = None
            
            # 使用线程池并行调用
            with ThreadPoolExecutor(max_workers=2) as executor:
                embedding_future = executor.submit(self.embedding_client.get_embedding, cover_link)
                ocr_future = executor.submit(self.ocr_client.extract_text, cover_link)
                
                embedding = embedding_future.result()
                ocr_text = ocr_future.result()
            
            if embedding is None:
                return None, "向量化失败"
            
            # 3. 原始 OCR 文本（str），不做进一步结构化处理
            ocr_raw: str = ocr_text or ""
            
            # 4. 组装数据
            result = {
                "mysql_id": mysql_id,
                "sku": sku,
                "isbn": isbn,
                "author": author,
                "cover_link": cover_link,
                "cover_hash": cover_hash,
                "embedding": embedding,
                "ocr_text": ocr_raw,
            }
            
            return result, None
            
        except Exception as e:
            error_msg = f"处理记录失败: {str(e)}"
            logger.error(f"{error_msg}, mysql_id: {mysql_id}")
            return None, error_msg
    
    def process_batch(self, records: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        批量处理记录
        
        Args:
            records: 记录列表
        
        Returns:
            (成功结果列表, 失败记录列表)
        """
        results = []
        errors = []
        
        # 使用线程池并发处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_record = {
                executor.submit(self.process_single_record, record): record
                for record in records
            }
            
            for future in as_completed(future_to_record):
                record = future_to_record[future]
                try:
                    result, error = future.result()
                    if result:
                        results.append(result)
                    else:
                        errors.append({
                            "record": record,
                            "error": error
                        })
                except Exception as e:
                    errors.append({
                        "record": record,
                        "error": str(e)
                    })
        logger.info(f"成功处理结果: {results}")
        logger.info(f"失败处理结果: {errors}")
        return results, errors
    
    def run(
        self,
        start_offset: Optional[int] = None,
        max_records: Optional[int] = None,
        reset_progress: bool = False
    ):
        """
        运行批量处理（按 id 分页，使用 last_processed_id 断点续跑）。

        Args:
            start_offset: 起始 id：本次从 id > start_offset 开始取（None 则从进度文件 last_processed_id 继续）
            max_records: 最大处理记录数（None 则处理全部）
            reset_progress: 是否重置进度
        """
        if reset_progress:
            self.progress_tracker.reset()
            logger.info("进度已重置")

        # 下次拉取的起始 id（None 表示从表内最小 id 开始）
        last_processed_id = (
            start_offset
            if start_offset is not None
            else self.progress_tracker.get_last_processed_id()
        )

        progress = self.progress_tracker.load()
        total_processed = progress.get("processed", 0)
        total_success = progress.get("success", 0)
        total_failed = progress.get("failed", 0)
        failed_records = progress.get("failed_records", [])

        logger.info(
            f"开始批量处理，从 id > {last_processed_id} 开始取，批次大小: {self.batch_size}"
        )

        while True:
            # 1. 按 id 分页拉取一批（WHERE id > last_processed_id ORDER BY id LIMIT）
            records = self.mysql_client.fetch_batch(
                limit=self.batch_size,
                last_processed_id=last_processed_id,
            )

            if not records:
                logger.info("没有更多数据，处理完成")
                break

            logger.info(f"获取到 {len(records)} 条记录，开始处理...")

            # 2. 批量处理
            start_time = time.time()
            results, errors = self.process_batch(records)
            process_time = time.time() - start_time

            # 3. 写入向量库
            if results:
                try:
                    self.vector_store.insert(results)
                    logger.info(
                        f"成功处理 {len(results)} 条，写入向量库，耗时: {process_time:.2f}秒"
                    )
                except Exception as e:
                    logger.error(f"向量库写入失败: {e}")
                    for result in results:
                        errors.append({
                            "record": {"id": result["mysql_id"]},
                            "error": f"向量库写入失败: {e}"
                        })
                    results = []

            # 4. 失败记录持久化到 JSONL，供后续统一重试
            for item in errors:
                self.failed_store.append(item["record"], item["error"])

            # 5. 更新进度：本批最大 id 作为下次 last_processed_id
            total_processed += len(records)
            total_success += len(results)
            total_failed += len(errors)
            failed_records.extend(errors)
            last_processed_id = records[-1]["id"]

            self.progress_tracker.update(
                offset=total_processed,
                processed=total_processed,
                success=total_success,
                failed=total_failed,
                failed_records=failed_records[-100:],
                last_processed_id=last_processed_id,
            )

            logger.info(
                f"进度: 总计={total_processed}, "
                f"成功={total_success}, "
                f"失败={total_failed}, "
                f"last_processed_id={last_processed_id}, "
                f"当前批次耗时={process_time:.2f}秒"
            )

            # 6. 是否达到本次最大处理数
            if max_records and total_processed >= max_records:
                logger.info(f"达到最大处理记录数: {max_records}")
                break

            time.sleep(0.1)
        
        logger.info(
            f"批量处理完成！"
            f"总计: {total_processed}, "
            f"成功: {total_success}, "
            f"失败: {total_failed}"
        )
    
    def close(self):
        """关闭所有连接"""
        self.mysql_client.close()
        self.vector_store.close()
        logger.info("所有连接已关闭")
