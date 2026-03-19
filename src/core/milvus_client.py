"""Milvus客户端模块（基于 pymilvus.MilvusClient）"""
from typing import List, Dict, Optional
from pymilvus import MilvusClient as PyMilvusClient, DataType
from loguru import logger
from src.utils.config import get_settings


class MilvusClient:
    """Milvus 客户端封装，内部使用 pymilvus.MilvusClient"""

    def __init__(self):
        """初始化 Milvus 客户端"""
        settings = get_settings()
        milvus_config = settings.milvus

        uri = f"http://{milvus_config.host}:{milvus_config.port}"
        self._client = PyMilvusClient(
            uri=uri,
            user=milvus_config.user or "",
            password=milvus_config.password or "",
        )

        self.collection_name = milvus_config.collection_name
        self.metric_type = milvus_config.metric_type
        self.index_type = milvus_config.index_type
        self.nlist = milvus_config.nlist
        self.nprobe = milvus_config.nprobe
        self.M = milvus_config.M
        self.ef_construction = milvus_config.ef_construction
        self.ef = milvus_config.ef

        logger.info(
            f"Milvus客户端初始化完成，Collection: {self.collection_name}, 索引: {self.index_type}"
        )

    def create_collection(self, force: bool = False):
        """
        创建 Collection

        Args:
            force: 如果 Collection 已存在，是否删除重建
        """
        if self._client.has_collection(collection_name=self.collection_name):
            if force:
                logger.warning(f"Collection {self.collection_name} 已存在，删除重建")
                self._client.drop_collection(collection_name=self.collection_name)
            else:
                logger.info(f"Collection {self.collection_name} 已存在")
                return

        schema = self._client.create_schema(auto_id=False)
        schema.add_field(
            field_name="id",
            datatype=DataType.INT64,
            is_primary=True,
            description="主键ID",
        )
        schema.add_field(
            field_name="mysql_id",
            datatype=DataType.INT64,
            description="MySQL中的原始ID",
        )
        schema.add_field(
            field_name="sku",
            datatype=DataType.VARCHAR,
            max_length=128,
            description="商品SKU",
        )
        schema.add_field(
            field_name="isbn",
            datatype=DataType.VARCHAR,
            max_length=32,
            description="ISBN号",
        )
        schema.add_field(
            field_name="author",
            datatype=DataType.VARCHAR,
            max_length=256,
            description="书籍作者",
        )
        schema.add_field(
            field_name="cover_link",
            datatype=DataType.VARCHAR,
            max_length=512,
            description="图片链接",
        )
        schema.add_field(
            field_name="cover_hash",
            datatype=DataType.VARCHAR,
            max_length=16,
            description="感知哈希",
        )
        schema.add_field(
            field_name="ocr_text",
            datatype=DataType.VARCHAR,
            max_length=8192,
            description="OCR 原始全文",
        )
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,
            description="图片向量",
        )

        self._client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
        )

        index_params = PyMilvusClient.prepare_index_params()
        if self.index_type.upper() == "IVF_FLAT":
            index_params.add_index(
                field_name="embedding",
                index_type="IVF_FLAT",
                metric_type=self.metric_type,
                params={"nlist": self.nlist},
            )
        else:
            index_params.add_index(
                field_name="embedding",
                index_type=self.index_type,
                metric_type=self.metric_type,
                params={
                    "M": self.M,
                    "efConstruction": self.ef_construction,
                },
            )

        self._client.create_index(
            collection_name=self.collection_name,
            index_params=index_params,
            sync=True,
        )

        logger.info(f"Collection {self.collection_name} 创建成功")

    def get_collection(self):
        """返回底层 MilvusClient，便于兼容原有调用；实际操作均通过 _client 完成"""
        return self._client

    def insert(self, data: List[Dict]):
        """
        插入数据

        Args:
            data: 数据列表，每个元素包含所有字段
        """
        if not data:
            return

        rows = []
        for i, item in enumerate(data):
            rows.append({
                "id": item.get("id", i),
                "mysql_id": item.get("mysql_id", 0),
                "sku": item.get("sku", ""),
                "isbn": item.get("isbn", ""),
                "author": (item.get("author") or "")[:256],
                "cover_link": item.get("cover_link", ""),
                "cover_hash": item.get("cover_hash", ""),
                "ocr_text": (item.get("ocr_text") or "")[:8192],
                "embedding": item.get("embedding", []),
            })

        self._client.insert(
            collection_name=self.collection_name,
            data=rows,
        )

        logger.info(f"成功插入 {len(data)} 条数据到Milvus")

    def search(
        self,
        query_vectors: List[List[float]],
        top_k: int = 5,
        output_fields: Optional[List[str]] = None,
        expr: Optional[str] = None,
    ) -> List[List[Dict]]:
        """
        向量检索

        Args:
            query_vectors: 查询向量列表
            top_k: 返回 Top-K 结果
            output_fields: 需要返回的字段列表
            expr: 过滤表达式（可选）

        Returns:
            检索结果列表，每个查询向量对应一个结果列表
        """
        if output_fields is None:
            output_fields = [
                "mysql_id",
                "sku",
                "isbn",
                "author",
                "cover_link",
                "ocr_text",
            ]

        if self.index_type.upper() == "IVF_FLAT":
            search_params = {"nprobe": self.nprobe}
        else:
            search_params = {"ef": self.ef}

        results = self._client.search(
            collection_name=self.collection_name,
            data=query_vectors,
            limit=top_k,
            output_fields=output_fields,
            filter=expr,
            search_params=search_params,
        )

        formatted_results = []
        for result in results:
            hits = []
            for hit in result:
                entity = hit.get("entity", hit)
                hit_dict = {
                    "id": hit.get("id"),
                    "score": hit.get("distance"),
                    "distance": hit.get("distance"),
                }
                for field in output_fields:
                    hit_dict[field] = entity.get(field) if isinstance(entity, dict) else getattr(entity, field, None)
                hits.append(hit_dict)
            formatted_results.append(hits)

        logger.debug(f"向量检索完成，返回 {len(formatted_results)} 组结果")
        return formatted_results

    def count(self) -> int:
        """获取 Collection 中的记录数"""
        from pymilvus.client.types import LoadState
        load_state_info  = self._client.is_collection_loaded(collection_name=self.collection_name)
        state = load_state_info["state"]
        if state is not LoadState.Loaded:
            self._client.load_collection(collection_name=self.collection_name)
        return self._client.query(collection_name=self.collection_name, output_fields=["count(*)"])

    def close(self):
        """关闭连接"""
        if hasattr(self._client, "close"):
            self._client.close()
        logger.info("Milvus连接已关闭")
