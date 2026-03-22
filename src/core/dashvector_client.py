"""阿里云 DashVector 客户端封装（与 MilvusClient 对外方法对齐）"""
from __future__ import annotations

from typing import Dict, List, Optional

import dashvector
from dashvector import Doc
from dashvector.common.error import DashVectorCode
from loguru import logger

from src.utils.config import get_settings


def _require_ok(rsp, operation: str) -> None:
    if not rsp:
        raise RuntimeError(
            f"DashVector {operation} 失败: code={rsp.code}, message={rsp.message}"
        )


class DashVectorClient:
    """DashVector 封装，insert/search/count 等与 MilvusClient 保持一致便于切换后端"""

    _FIELD_SCHEMA = {
        "mysql_id": int,
        "sku": str,
        "isbn": str,
        "author": str,
        "cover_link": str,
        "cover_hash": str,
        "ocr_text": str,
    }

    def __init__(self):
        settings = get_settings()
        dv = settings.dashvector
        api_key = (dv.api_key or "").strip() or (settings.aliyun.api_key or "").strip()
        endpoint = (dv.endpoint or "").strip()
        if not endpoint:
            raise ValueError("使用 DashVector 时请在配置 dashvector.endpoint 中填写集群 endpoint")
        if not api_key:
            raise ValueError(
                "使用 DashVector 时请配置 dashvector.api_key 或 aliyun.api_key"
            )

        self._client = dashvector.Client(api_key=api_key, endpoint=endpoint)
        _require_ok(self._client, "连接初始化")

        self.collection_name = dv.collection_name
        self._metric = (dv.metric or "cosine").strip().lower()
        self._dimension = settings.aliyun.embedding_dimension

        logger.info(
            f"DashVector 客户端初始化完成，Collection: {self.collection_name}, "
            f"metric={self._metric}, dim={self._dimension}"
        )

    def _collection(self):
        col = self._client.get(self.collection_name)
        if not col:
            raise RuntimeError(
                f"获取 DashVector Collection 失败: {col.code} {col.message}"
            )
        return col

    def create_collection(self, force: bool = False):
        desc = self._client.describe(self.collection_name)
        if desc.code == DashVectorCode.Success:
            if not force:
                logger.info(f"DashVector Collection {self.collection_name} 已存在")
                return
            logger.warning(f"DashVector Collection {self.collection_name} 已存在，删除重建")
            del_rsp = self._client.delete(self.collection_name)
            _require_ok(del_rsp, "delete_collection")

        create_rsp = self._client.create(
            name=self.collection_name,
            dimension=self._dimension,
            metric=self._metric,
            fields_schema=dict(self._FIELD_SCHEMA),
        )
        _require_ok(create_rsp, "create_collection")
        logger.info(f"DashVector Collection {self.collection_name} 创建成功")

    def insert(self, data: List[Dict]):
        if not data:
            return

        docs = []
        for item in data:
            mysql_id = item.get("mysql_id", 0)
            doc_id = str(mysql_id)
            fields = {
                "mysql_id": int(mysql_id),
                "sku": item.get("sku", "") or "",
                "isbn": item.get("isbn", "") or "",
                "author": ((item.get("author") or "")[:256]),
                "cover_link": item.get("cover_link", "") or "",
                "cover_hash": item.get("cover_hash", "") or "",
                "ocr_text": ((item.get("ocr_text") or "")[:8192]),
            }
            vec = item.get("embedding", [])
            docs.append(Doc(id=doc_id, vector=vec, fields=fields))

        col = self._collection()
        rsp = col.upsert(docs)
        _require_ok(rsp, "upsert")
        logger.info(f"成功 upsert {len(data)} 条数据到 DashVector")

    def _metric_to_similarity(self, raw: float) -> tuple[float, float]:
        """
        DashVector query 返回的 score 含义随 metric 不同，与 Milvus 检索里用于阈值的「越大越相似」需对齐。

        cosine：官方定义为余弦距离 = 1 - 余弦相似度，取值约 [0, 2]，越小越相似。
        此处将余弦相似度 = 1 - 余弦距离，并限制在 [0, 1]，供 /search 与 Milvus 相同的 threshold 使用。

        dotproduct：点积越大越相似，与阈值方向一致，直接作为 score。

        euclidean：距离越小越相似；未做归一化，与 0.95/0.85 阈值不可直接类比。
        参考：https://help.aliyun.com/document_detail/2584947.html
        """
        r = float(raw)
        m = self._metric
        if m == "cosine":
            sim = 1.0 - r
            return (max(0.0, min(1.0, sim)), r)
        if m == "dotproduct":
            return (r, r)
        return (r, r)

    def search(
        self,
        query_vectors: List[List[float]],
        top_k: int = 5,
        output_fields: Optional[List[str]] = None,
        expr: Optional[str] = None,
    ) -> List[List[Dict]]:
        if output_fields is None:
            output_fields = [
                "mysql_id",
                "sku",
                "isbn",
                "author",
                "cover_link",
                "ocr_text",
            ]

        col = self._collection()
        filter_expr = expr
        formatted: List[List[Dict]] = []

        for qv in query_vectors:
            rsp = col.query(
                vector=qv,
                topk=top_k,
                output_fields=output_fields,
                filter=filter_expr,
                include_vector=False,
            )
            _require_ok(rsp, "query")
            hits = []
            for doc in rsp.output or []:
                fid = doc.fields.get("mysql_id") if doc.fields else None
                if fid is None:
                    try:
                        fid = int(doc.id) if doc.id is not None else 0
                    except ValueError:
                        fid = 0
                sim, raw_metric = self._metric_to_similarity(doc.score)
                hit_dict: Dict = {
                    "id": int(fid) if fid is not None else 0,
                    "score": sim,
                    "distance": raw_metric,
                }
                for field in output_fields:
                    if doc.fields and field in doc.fields:
                        hit_dict[field] = doc.fields[field]
                    else:
                        hit_dict[field] = None
                hits.append(hit_dict)
            formatted.append(hits)

        logger.debug(f"DashVector 检索完成，返回 {len(formatted)} 组结果")
        return formatted

    def count(self) -> int:
        col = self._collection()
        rsp = col.stats()
        _require_ok(rsp, "stats")
        out = rsp.output
        if out is None:
            return 0
        n = out.total_doc_count
        if n is None:
            return 0
        return int(n)

    def close(self):
        self._client.close()
        logger.info("DashVector 连接已关闭")
