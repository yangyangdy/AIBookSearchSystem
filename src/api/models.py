"""API数据模型"""
from typing import Optional, List
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class SearchRequest(BaseModel):
    """搜索请求"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "image_url": "https://example.com/cover.jpg",
                "top_k": 10,
                "similarity_threshold1": 0.95,
                "similarity_threshold2": 0.85,
                "use_ocr_text_refinement": True,
                "ocr_similarity_threshold": 0.8,
            }
        },
    )

    image_url: Optional[HttpUrl] = Field(None, description="图片URL")
    image_base64: Optional[str] = Field(None, description="Base64编码的图片")
    top_k: int = Field(default=5, ge=1, le=100, description="返回Top-K结果")
    similarity_threshold1: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="向量相似度高阈值：score >= 此值视为与查询图一致，直接返回",
    )
    similarity_threshold2: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="向量相似度低阈值：无高阈值命中时，仅保留 score >= 此值的候选，取最高分做 OCR 比对",
    )
    use_ocr_text_refinement: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "use_ocr_text_refinement", "useOcrTextRefinement"
        ),
        description="为 True 时：对查询图 OCR，与候选的 ocr_text 比对，仅保留 OCR 判定为相似的条目",
    )
    ocr_similarity_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="OCR 文本相似度阈值：比对得分 >= 此值视为通过，用于低阈值候选的二次判定",
    )

    @model_validator(mode="after")
    def check_threshold_order(self):
        if self.similarity_threshold1 <= self.similarity_threshold2:
            raise ValueError("similarity_threshold1 必须大于 similarity_threshold2")
        return self


class SearchResultItem(BaseModel):
    """搜索结果项"""
    id: int = Field(..., description="Milvus ID")
    mysql_id: int = Field(..., description="MySQL ID")
    sku: str = Field(..., description="商品SKU")
    isbn: str = Field(..., description="ISBN号")
    author: Optional[str] = Field(None, description="书籍作者")
    cover_link: str = Field(..., description="图片链接")
    similarity: float = Field(..., description="相似度分数")
    ocr_text: Optional[str] = Field(None, description="OCR 原始全文")
    ocr_match_score: Optional[float] = Field(
        None,
        description="开启 OCR 比较且保留时，查询图 OCR 与该条 ocr_text 的相似度 [0,1]",
    )


class SearchResponse(BaseModel):
    """搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")
    total: int = Field(..., description="结果总数")
    results: List[SearchResultItem] = Field(..., description="搜索结果列表")
    refinement_applied: Optional[bool] = Field(
        None, description="是否实际执行了查询图 OCR 与 ocr_text 的二次比对筛选"
    )
    refinement_detail: Optional[str] = Field(
        None, description="二次比对说明（候选条数、通过条数、跳过原因等）"
    )


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="状态")
    version: str = Field(..., description="版本")
    milvus_connected: bool = Field(..., description="Milvus连接状态")
    milvus_count: Optional[int] = Field(None, description="Milvus记录数")
