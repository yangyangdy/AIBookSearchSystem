"""搜索接口"""
import base64
import re
from typing import List, Optional, Set, Tuple
from fastapi import APIRouter, HTTPException
from loguru import logger

from src.api.models import SearchRequest, SearchResponse, SearchResultItem
from src.core.vector_store import get_vector_store
from src.core.embedding_client import EmbeddingClient
from src.core.image_processor import ImageProcessor
from src.core.ocr_client import OCRClient
from src.utils.config import get_settings
from src.utils.search_image_compress import (
    compress_search_image_bytes,
    decode_base64_to_bytes,
)

router = APIRouter(prefix="/api/v1", tags=["search"])

_embedding_client: EmbeddingClient = None
_ocr_client: OCRClient = None

_OCR_COMPARE_LEN = 400
_SIG_CHAR = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
# 单词：连续字母数字 或 连续汉字（便于中英文统一处理）
_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")

def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def get_ocr_client() -> OCRClient:
    global _ocr_client
    if _ocr_client is None:
        _ocr_client = OCRClient()
    return _ocr_client


def _sig_char_set(s: str) -> Set[str]:
    return set(_SIG_CHAR.findall((s or "").lower()))


def _cjk_bigrams(s: str) -> List[str]:
    chs = [c for c in (s or "") if "\u4e00" <= c <= "\u9fff"]
    if len(chs) < 2:
        return []
    return [chs[i] + chs[i + 1] for i in range(len(chs) - 1)]


def _word_set(s: str) -> Set[str]:
    """
    按单词/连续汉字切分：连续字母数字算一个 token，连续汉字算 token，
    统一小写（仅对字母），用于单词级匹配。
    """
    raw = (s or "").strip()[:_OCR_COMPARE_LEN]
    tokens = _WORD_PATTERN.findall(raw)
    return set(t.lower() if t[0].isascii() else t for t in tokens if t)


# OCR 二次比对时，得分 >= 该阈值视为通过（默认 0.8，可由请求参数 ocr_similarity_threshold 覆盖）
_DEFAULT_OCR_SIMILARITY_THRESHOLD = 0.8


def compare_ocr_for_candidate(
    query_ocr: str,
    record_ocr_text: str,
    ocr_similarity_threshold: float = _DEFAULT_OCR_SIMILARITY_THRESHOLD,
) -> Tuple[bool, str]:
    """
    对「查询图 OCR 文本」与「候选条目的 ocr_text」进行比对，判断是否视为同一封面。
    仅在「无 score >= threshold1、存在 score >= threshold2 的候选」时，对分数最高的那条调用。
    通过 ocr_similarity_query_vs_record_ocr_text 获取得分，>= ocr_similarity_threshold 则通过。
    返回 (是否通过, 说明文案：含得分与原因)。
    """
    score = ocr_similarity_query_vs_record_ocr_text(query_ocr, record_ocr_text)
    passed = score >= ocr_similarity_threshold
    reason = "通过" if passed else "未通过"
    detail = f"OCR 相似度 {score:.4f}，阈值 {ocr_similarity_threshold}，{reason}"
    return (passed, detail)


def ocr_similarity_query_vs_record_ocr_text(query_ocr: str, record_ocr_text: str) -> float:
    """
    查询图 OCR 与单条检索结果的 ocr_text 字段的相似度 [0,1]。
    查询来自封面 OCR，通常含较多无关描述词；候选为库内书籍的 ocr_text。
    - 英文等：按单词切分、统一小写后，用「候选单词被查询覆盖的比例」作为主指标：
      word_coverage = |q_words ∩ c_words| / |c_words|，即候选里有多少比例的词在查询里出现。
    - 中文：保留「字符召回 + 汉字二元组命中」。
    """
    cand = (record_ocr_text or "").strip()[:_OCR_COMPARE_LEN]
    q = (query_ocr or "").strip()[:_OCR_COMPARE_LEN]
    if not q or not cand:
        return 0.0

    # 单词级：候选单词被查询覆盖的比例（更贴合「查询是带噪封面、候选是书籍标识」）
    q_words = _word_set(q)
    c_words = _word_set(cand)
    word_coverage = len(q_words & c_words) / len(c_words) if c_words else 0.0

    # 字符级（兼容短文本、纯符号等）
    qset = _sig_char_set(q)
    cset = _sig_char_set(cand)
    if not qset:
        return word_coverage
    char_recall = len(qset & cset) / len(qset)

    # 中文：使用汉字二元组
    bigs = _cjk_bigrams(q)
    if bigs:
        cand_compact = re.sub(r"\s+", "", cand)
        bi_hit = sum(1 for bg in set(bigs) if bg in cand_compact) / len(set(bigs))
        char_score = min(1.0, 0.55 * char_recall + 0.45 * bi_hit)
        return max(char_score, word_coverage) if c_words else char_score
    # 英文或无语义单元：优先用候选被查询覆盖的比例，否则退回字符召回
    return word_coverage if c_words else char_recall


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    双阈值检索逻辑：
    1) 向量检索后，若存在 score >= similarity_threshold1 的图片，视为与查询图一致，直接返回（取 top_k）；
    2) 若不存在 score >= similarity_threshold1，则检查 score >= similarity_threshold2：
       - 若不存在则返回空；
       - 若存在多条，取分数最高的一条，进行 ocr_text 比对（compare_ocr_for_candidate）；
       - 比对通过则返回该条，否则返回空。
    """
    try:
        vector_store = get_vector_store()
        embedding_client = get_embedding_client()
        icfg = get_settings().api.search_image_compress

        embedding_src_url: Optional[str] = None
        embedding_src_b64: Optional[str] = None

        if request.image_url:
            embedding = embedding_client.get_embedding(str(request.image_url))
            if icfg.enabled:
                ip = ImageProcessor()
                raw = ip.download_image(str(request.image_url))
                if raw is None:
                    raise HTTPException(status_code=400, detail="图片下载失败")
                try:
                    prepared = compress_search_image_bytes(raw, icfg)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                embedding_src_b64 = base64.standard_b64encode(prepared).decode("ascii")
            else:
                embedding_src_url = str(request.image_url)
        elif request.image_base64:
            if icfg.enabled:
                try:
                    raw = decode_base64_to_bytes(request.image_base64)
                except Exception:
                    raise HTTPException(status_code=400, detail="Base64 解码失败")
                try:
                    prepared = compress_search_image_bytes(raw, icfg)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                embedding_src_b64 = base64.standard_b64encode(prepared).decode("ascii")
            else:
                embedding_src_b64 = request.image_base64
        else:
            raise HTTPException(status_code=400, detail="必须提供image_url或image_base64")

        if embedding_src_url is not None:
            embedding = embedding_client.get_embedding(embedding_src_url)
        else:
            embedding = embedding_client.get_embedding_from_base64(embedding_src_b64)

        if embedding is None:
            raise HTTPException(status_code=500, detail="向量化失败")

        thr1 = request.similarity_threshold1
        thr2 = request.similarity_threshold2

        search_results = vector_store.search(
            query_vectors=[embedding],
            top_k= max(request.top_k , 1),
            output_fields=[
                "mysql_id", "sku", "isbn", "author", "cover_link", "ocr_text",
            ],
        )

        if not search_results or not search_results[0]:
            return SearchResponse(
                success=True,
                message="未找到匹配结果",
                total=0,
                results=[],
                refinement_applied=False,
                refinement_detail=None,
            )

        hits = search_results[0]
        hits_sorted = sorted(
            hits,
            key=lambda x: float(x.get("score") or 0),
            reverse=True,
        )

        tier1 = [h for h in hits_sorted if float(h.get("score") or 0) >= thr1]
        tier2 = [h for h in hits_sorted if float(h.get("score") or 0) >= thr2]

        msg_extra = ""
        refinement_applied: bool | None = None
        refinement_detail: str | None = None
        filtered_results: List[dict] = []
        ocr_scores_by_id: dict = {}

        if tier1:
            # 区分数最高的一个返回（保持为列表以便后续统一遍历）
            filtered_results = [tier1[0]]
            refinement_applied = False
            refinement_detail = f"存在 score>={thr1} 的候选，直接返回（一致）"
        else:
            if not tier2:
                refinement_applied = False
                refinement_detail = (
                    f"无 score>={thr1} 且无 score>={thr2} 的候选，返回空"
                )
                msg_extra = "（无符合阈值的向量结果）"
            else:
                if not request.use_ocr_text_refinement:
                    filtered_results = []
                    refinement_applied = False
                    refinement_detail = (
                        f"无 score>={thr1}，存在 score>={thr2} 的候选，但 OCR 二次比对开关未打开，返回空"
                    )
                    msg_extra = "（请开启 OCR 二次比对以对低阈值候选进行比对）"
                else:
                    best = tier2[0]
                    ocr_client = get_ocr_client()
                    if embedding_src_url is not None:
                        query_ocr = ocr_client.extract_text(embedding_src_url)
                    else:
                        query_ocr = ocr_client.extract_text_from_base64(
                            embedding_src_b64 or ""
                        )
                    qstrip = (query_ocr or "").strip()
                    if not qstrip:
                        logger.warning("查询图 OCR 为空，无法进行 ocr_text 比对")
                        filtered_results = []
                        refinement_applied = False
                        refinement_detail = "查询图 OCR 无有效文字，未通过二次比对"
                        msg_extra = "（查询图 OCR 失败）"
                    else:
                        passed, ocr_detail = compare_ocr_for_candidate(
                            qstrip,
                            best.get("ocr_text") or "",
                            request.ocr_similarity_threshold,
                        )
                        refinement_applied = True
                        refinement_detail = (
                            f"无 score>={thr1}，取 score>={thr2} 最高分一条进行 OCR 比对；{ocr_detail}"
                        )
                        if passed:
                            filtered_results = [best]
                        else:
                            filtered_results = []
                            msg_extra = "（OCR 比对未通过）"

        result_items = []
        for hit in filtered_results:
            oid = id(hit)
            result_items.append(
                SearchResultItem(
                    id=hit["id"],
                    mysql_id=hit.get("mysql_id", 0),
                    sku=hit.get("sku", ""),
                    isbn=hit.get("isbn", ""),
                    author=hit.get("author"),
                    cover_link=hit.get("cover_link", ""),
                    similarity=hit["score"],
                    ocr_text=hit.get("ocr_text"),
                    ocr_match_score=ocr_scores_by_id.get(oid) if ocr_scores_by_id else None,
                )
            )

        base_msg = "搜索成功"
        if not result_items:
            base_msg = "未找到符合条件的结果"

        return SearchResponse(
            success=True,
            message=base_msg + msg_extra,
            total=len(result_items),
            results=result_items,
            refinement_applied=refinement_applied,
            refinement_detail=refinement_detail,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")
