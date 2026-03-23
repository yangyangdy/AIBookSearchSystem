"""配置管理模块"""
import os
from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
import yaml

class SearchImageCompressConfig(BaseModel):
    """POST /search 查询图压缩（批量入库不使用）"""

    enabled: bool = Field(default=True, description="是否启用")
    max_bytes: int = Field(
        default=1_048_576, description="目标最大字节数（不超过则跳过压缩）"
    )
    max_long_edge: int = Field(default=2048, description="长边像素上限（迭代缩小起点）")
    min_long_edge: int = Field(default=640, description="长边缩小下限")
    jpeg_quality_start: int = Field(default=85, description="JPEG 初始质量 1-95")
    jpeg_quality_min: int = Field(default=50, description="JPEG 最低质量")

class MySQLConfig(BaseSettings):
    """MySQL配置"""
    host: str = Field(default="localhost", description="MySQL主机")
    port: int = Field(default=3306, description="MySQL端口")
    user: str = Field(..., description="MySQL用户名")
    password: str = Field(..., description="MySQL密码")
    database: str = Field(..., description="数据库名")
    table_name: str = Field(default="book_info_table", description="表名")
    pool_size: int = Field(default=10, description="连接池大小")
    max_overflow: int = Field(default=20, description="最大溢出连接数")

    class Config:
        env_prefix = "MYSQL_"
        case_sensitive = False


class MilvusConfig(BaseSettings):
    """Milvus配置"""
    host: str = Field(default="localhost", description="Milvus主机")
    port: int = Field(default=19530, description="Milvus端口")
    user: str = Field(default="", description="Milvus用户名（空则无认证）")
    password: str = Field(default="", description="Milvus密码")
    collection_name: str = Field(default="book_cover_vectors", description="Collection名称")
    metric_type: str = Field(default="COSINE", description="相似度计算方式")
    index_type: str = Field(default="IVF_FLAT", description="索引类型: IVF_FLAT / HNSW")
    nlist: int = Field(default=1024, description="IVF_FLAT 聚类中心数")
    nprobe: int = Field(default=16, description="IVF_FLAT 搜索时探测的桶数")
    M: int = Field(default=16, description="HNSW参数M")
    ef_construction: int = Field(default=200, description="HNSW参数efConstruction")
    ef: int = Field(default=64, description="HNSW搜索参数ef")

    class Config:
        env_prefix = "MILVUS_"
        case_sensitive = False

class DashVectorConfig(BaseSettings):
    """阿里云 DashVector 配置（vector_backend=dashvector 时必填 endpoint；api_key 为空则使用 aliyun.api_key）"""

    endpoint: str = Field(default="", description="DashVector 集群 endpoint")
    collection_name: str = Field(
        default="book_cover_vectors", description="Collection 名称"
    )
    api_key: str = Field(default="", description="为空则使用 aliyun.api_key")
    metric: str = Field(
        default="cosine", description="距离度量：cosine / dotproduct / euclidean"
    )

    class Config:
        env_prefix = "DASHVECTOR_"
        case_sensitive = False

class AliyunConfig(BaseSettings):
    """阿里云配置"""
    api_key: str = Field(..., description="阿里云API Key")
    embedding_model: str = Field(
        default="qwen3-vl-embedding", description="向量化模型（MultiModalEmbedding）"
    )
    embedding_dimension: int = Field(
        default=1024, description="向量维度，需与当前向量库（Milvus / DashVector）一致"
    )
    ocr_service: str = Field(default="aliyun_ocr", description="OCR服务")
    ocr_model: str = Field(
        default="qwen-vl-ocr-latest", description="OCR 多模态模型（MultiModalConversation）"
    )

    class Config:
        env_prefix = "ALIYUN_"
        case_sensitive = False


class ProcessingConfig(BaseSettings):
    """处理配置"""
    batch_size: int = Field(default=1000, description="每批处理数量")
    max_workers: int = Field(default=10, description="并发线程数")
    retry_times: int = Field(default=3, description="重试次数")
    timeout: int = Field(default=30, description="超时时间（秒）")
    image_download_timeout: int = Field(default=10, description="图片下载超时（秒）")

    class Config:
        env_prefix = ""
        case_sensitive = False


class APIConfig(BaseSettings):
    """API配置"""
    host: str = Field(default="0.0.0.0", description="API主机")
    port: int = Field(default=8000, description="API端口")
    title: str = Field(default="书籍封面向量检索系统", description="API标题")
    version: str = Field(default="1.0.0", description="API版本")
    search_image_compress: SearchImageCompressConfig = Field(
        default_factory=SearchImageCompressConfig,
        description="检索上传图压缩",
    )

    class Config:
        env_prefix = "API_"
        case_sensitive = False


class LoggingConfig(BaseSettings):
    """日志配置"""
    level: str = Field(default="INFO", description="日志级别")
    file: str = Field(default="logs/app.log", description="默认日志文件（未指定 profile 时使用）")
    api_file: str = Field(default="logs/api.log", description="API 入口日志文件")
    batch_file: str = Field(default="logs/batch.log", description="批量处理日志文件")
    rotation: str = Field(default="10 MB", description="日志轮转大小")
    retention: str = Field(default="7 days", description="日志保留时间")

    class Config:
        env_prefix = "LOG_"
        case_sensitive = False


class Settings(BaseSettings):
    """全局配置"""
    vector_backend: Literal["milvus", "dashvector"] = Field(
        default="dashvector", description="向量库：milvus 或 dashvector"
    )
    mysql: MySQLConfig
    milvus: MilvusConfig
    dashvector: DashVectorConfig
    aliyun: AliyunConfig
    processing: ProcessingConfig
    api: APIConfig
    logging: LoggingConfig

    @classmethod
    def load_from_yaml(cls, config_path: Optional[str] = None) -> "Settings":
        """从YAML文件加载配置"""
        if config_path is None:
            config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
        
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        vb_raw = config_data.get("vector_backend", "milvus")
        if isinstance(vb_raw, str):
            vb = vb_raw.strip().lower()
        else:
            vb = "milvus"
        if vb not in ("milvus", "dashvector"):
            raise ValueError(
                f"无效 vector_backend: {vb_raw!r}，仅支持 milvus、dashvector"
            )

        return cls(
            vector_backend=vb,
            mysql=MySQLConfig(**config_data.get("mysql", {})),
            milvus=MilvusConfig(**config_data.get("milvus", {})),
            dashvector=DashVectorConfig(**config_data.get("dashvector", {})),
            aliyun=AliyunConfig(**config_data.get("aliyun", {})),
            processing=ProcessingConfig(**config_data.get("processing", {})),
            api=APIConfig(**config_data.get("api", {})),
            logging=LoggingConfig(**config_data.get("logging", {}))
        )

    @classmethod
    def load_from_env(cls) -> "Settings":
        """从环境变量加载配置"""
        vb_raw = os.getenv("VECTOR_BACKEND", "milvus")
        vb = vb_raw.strip().lower() if isinstance(vb_raw, str) else "milvus"
        if vb not in ("milvus", "dashvector"):
            vb = "milvus"
        return cls(
            vector_backend=vb,
            mysql=MySQLConfig(),
            milvus=MilvusConfig(),
            dashvector=DashVectorConfig(),
            aliyun=AliyunConfig(),
            processing=ProcessingConfig(),
            api=APIConfig(),
            logging=LoggingConfig()
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
_settings: Optional[Settings] = None


def _default_config_path() -> Optional[Path]:
    """返回默认配置文件路径（相对项目根），不存在则返回 None"""
    # 项目根：src/utils/config.py -> 上两级
    root = Path(__file__).resolve().parent.parent.parent
    path = root / "config" / "config.yaml"
    return path if path.exists() else None


def get_settings() -> Settings:
    """获取全局配置"""
    global _settings
    if _settings is None:
        # 优先从 YAML 加载：CONFIG_PATH 或项目根下的 config/config.yaml
        config_path = os.getenv("CONFIG_PATH")
        if config_path:
            config_path = Path(config_path)
        else:
            config_path = _default_config_path()
        if config_path is not None and Path(config_path).exists():
            _settings = Settings.load_from_yaml(str(config_path))
        else:
            _settings = Settings.load_from_env()
    return _settings
