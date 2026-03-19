# AIBookSearchSystem
# 书籍封面向量检索系统

基于向量检索的书籍封面相似性查找系统，支持通过图片快速检索相似的书籍封面。

> 📖 **详细文档**: 请查看 [docs/](docs/) 目录下的技术文档（部分章节可能与当前实现不完全一致，以本文与代码为准）

## 功能特性

- ✅ 从 MySQL 分批读取书籍信息（含封面链接、作者等）
- ✅ 图片向量化：阿里云 DashScope **MultiModalEmbedding**（如 `qwen3-vl-embedding`，维度可配置，与 Milvus 一致）
- ✅ OCR：DashScope **MultiModalConversation** 内置高精文字识别（`text_recognition`），批量流程写入 **原始 OCR 全文**（`ocr_text`），不再做书名/作者等结构化解析入库
- ✅ 向量存储与检索（Milvus，COSINE 等）
- ✅ 图片相似度搜索 API，返回 MySQL 作者（`author`）、原始 OCR（`ocr_text`）等
- ✅ **双阈值检索**：`similarity_threshold1` > `similarity_threshold2`；score ≥ 高阈值时取最高分一条返回；否则在低阈值候选中取最高分一条，若开启 **OCR 二次比对**（`use_ocr_text_refinement`）则调用 `compare_ocr_for_candidate`（基于 `ocr_similarity_query_vs_record_ocr_text` 与 `ocr_similarity_threshold` 判定），通过则返回该条，否则返回空；未开启则直接返回空
- ✅ 批量处理支持断点续传；失败记录写入 **JSONL**，与进度文件同目录

## 技术栈

- **Web 框架**: FastAPI
- **数据库**: MySQL (SQLAlchemy)
- **向量数据库**: Milvus（pymilvus MilvusClient）
- **向量化**: 阿里云 DashScope `MultiModalEmbedding`
- **OCR**: 阿里云 DashScope `MultiModalConversation`（OCR 专用模型）
- **图像处理**: Pillow, imagehash
- **分词（可选）**: jieba（`ocr_processor` 模块仍保留，当前批处理主流程未调用）

## 项目结构

```
imgsearchimg/
├── src/
│   ├── core/                 # 核心模块
│   │   ├── mysql_client.py
│   │   ├── milvus_client.py
│   │   ├── image_processor.py
│   │   ├── embedding_client.py
│   │   ├── ocr_client.py
│   │   └── ocr_processor.py  # 可选 OCR 后处理（批处理默认不用）
│   ├── batch/
│   │   ├── processor.py
│   │   ├── progress.py
│   │   └── failed_store.py
│   ├── api/
│   │   ├── main.py
│   │   ├── models.py
│   │   └── routes/
│   └── utils/
│       ├── config.py
│       └── logger.py
├── docs/
├── config/
│   └── config.example.yaml
├── scripts/
│   ├── init_milvus.py
│   ├── batch_process.py
│   └── import_xlsx_to_mysql.py  # XLSX 按列名导入 MySQL
├── static/                   # 检索页 index.html（GET /）
├── requirements.txt
├── run_api.py
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

编辑 `config/config.yaml` 与 `.env`：MySQL、Milvus、**阿里云 API Key**、模型与维度等。

### 3. 初始化 Milvus

```bash
python scripts/init_milvus.py
```

**升级说明**：若曾使用旧版 Collection（无 `author` / `ocr_text`、向量维度非 1024 等），需在代码中 `create_collection(force=True)` 或删除旧集后重建，并**重新跑批量入库**。

### 4. 批量处理数据

入口脚本：`scripts/batch_process.py`。执行前请完成 MySQL / Milvus / 阿里云配置，并已初始化 Milvus Collection。

#### 批处理在做什么（流程说明）

1. **断点与分页**：按 MySQL 主键 `id` 升序，每次取一批（条数由配置 `processing.batch_size` 决定），条件为 `id > last_processed_id`（首次或重置后为「从最小 id 开始」）。
2. **单条记录**：下载并校验封面图 → 计算感知哈希；**并行**调用向量化（Embedding）与 OCR；组装 `mysql_id`、`sku`、`isbn`、`author`、`cover_link`、`cover_hash`、`embedding`、`ocr_text`。
3. **写入 Milvus**：本批成功结果批量 `insert`；失败或插入异常记入错误列表。
4. **失败落盘**：每条失败对应一行写入与进度文件**同目录**的 **`failed_records.jsonl`**（JSON Lines，含原始 `record` 与 `error`）。
5. **更新进度**：将本批最后一条的 `id` 记为 `last_processed_id`，并累计 `processed` / `success` / `failed`；进度文件内仅保留最近约 100 条失败摘要便于查看，完整失败仍以 JSONL 为准。
6. **并发**：批与批之间串行；**批内**多条记录由 `processing.max_workers` 个线程并发处理（与 DashScope 限流需自行权衡）。

行为与参数还可通过 `python scripts/batch_process.py -h` 查看（含默认值）。

#### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--progress-file` | `progress.json` | 进度 JSON 路径。若文件不存在，**首次运行会自动创建**（含 `last_processed_id: null` 等）。父目录不存在会自动创建。 |
| `--offset ID` | 不设置（`None`） | 本次运行从 **`id > ID`** 开始拉取。不设时优先用进度文件里的 **`last_processed_id`** 续跑。与 `--reset` 联用时：先重置再按此处起始；若仍不设则从头扫表。 |
| `--max-records N` | 不限制 | 本轮累计**已拉取并进入处理的条数**（按批内记录数累加）达到 `N` 即停止，便于试跑或分段执行。 |
| `--reset` | 关闭 | **仅当命令行带上该 flag 时生效**。将进度文件重置为初始状态（`last_processed_id` 清空、计数归零等），**然后继续执行本趟批处理**（通常用于全量重导、换 Milvus 后重跑）。不会清空 Milvus 数据。 |

常用示例：

```bash
python scripts/batch_process.py
python scripts/batch_process.py --progress-file logs/run1/progress.json
python scripts/batch_process.py --offset 10000
python scripts/batch_process.py --max-records 500
python scripts/batch_process.py --reset
python scripts/batch_process.py --reset --max-records 1000
```

#### 与配置项的关系（`config.yaml` → `processing`）

| 配置项 | 作用 |
|--------|------|
| `batch_size` | 每轮从 MySQL 拉取的最大条数 |
| `max_workers` | 同时处理多少条记录（线程数） |

### 5. 启动 API

```bash
python run_api.py
# 或
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

- **图片检索页（上传本地图或填图片 URL）**：http://localhost:8000/（端口以 `config.yaml` 中 `api.port` 为准）
- **Swagger API 文档**：http://localhost:8000/docs

## API 使用

### 搜索

`POST /api/v1/search`

```json
{
  "image_url": "https://example.com/cover.jpg",
  "top_k": 5,
  "similarity_threshold1": 0.95,
  "similarity_threshold2": 0.85,
  "use_ocr_text_refinement": false,
  "ocr_similarity_threshold": 0.8
}
```

| 参数 | 说明 |
|------|------|
| `image_url` / `image_base64` | 查询图片（二选一） |
| `top_k` | 返回条数上限（高阈值命中时当前仅返回 1 条） |
| `similarity_threshold1` | 向量高阈值：score ≥ 此值视为与查询图一致 |
| `similarity_threshold2` | 向量低阈值：无高阈值命中时，仅考虑 score ≥ 此值的候选 |
| `use_ocr_text_refinement` | 为 `true` 时，在「仅命中低阈值」的情况下对最高分一条做 OCR 二次比对；为 `false` 时不做比对且该情况返回空 |
| `ocr_similarity_threshold` | OCR 文本相似度阈值（0～1），比对得分 ≥ 此值视为通过，默认 0.8 |

**要求**：`similarity_threshold1` 必须大于 `similarity_threshold2`。

**流程**：
1. 向量检索后，若存在 **score ≥ similarity_threshold1** 的图片，视为与查询图一致，取**分数最高的一条**返回。
2. 若不存在 score ≥ threshold1，则检查 **score ≥ similarity_threshold2**：
   - 若不存在则返回空；
   - 若存在：取**分数最高的一条**；
     - 若 **未开启** `use_ocr_text_refinement`：返回空，并说明请开启 OCR 二次比对；
     - 若 **已开启**：对查询图做 OCR，与候选的 `ocr_text` 通过 `ocr_similarity_query_vs_record_ocr_text` 计算相似度，得分 **≥ ocr_similarity_threshold** 则返回该条，否则返回空。`refinement_detail` 中会包含本次得分与阈值、通过/未通过原因。

**OCR 相似度计算**（`ocr_similarity_query_vs_record_ocr_text`）：英文等按单词切分、统一小写后，用「候选单词被查询覆盖的比例」作为主指标；中文保留字符召回 + 汉字二元组。返回 [0,1] 分数。

响应中含 `refinement_detail`（说明走高阈值直接返回、或低阈值+OCR 比对及得分/原因等）；无结果时也会带上该说明，便于排查。

### 健康检查

`GET /api/v1/health`

## 配置说明

### MySQL

- **表名**可配置（默认 `book_info_table`）
- 批量拉取要求存在字段：**`id`**, **`sku`**, **`isbn`**, **`cover_link`**, **`author`**（无作者可为空字符串，需有列）

### Milvus

- **向量维度**：默认 **1024**，与 `aliyun.embedding_dimension` 一致
- 标量字段：`mysql_id`, `sku`, `isbn`, `author`, `cover_link`, `cover_hash`, `ocr_text`（原始 OCR，VARCHAR 8192）

### 阿里云（DashScope）

| 配置项 | 说明 |
|--------|------|
| `api_key` | API Key（勿提交到仓库） |
| `embedding_model` | 多模态向量模型，默认 `qwen3-vl-embedding` |
| `embedding_dimension` | 向量维度，默认 1024，须与 Milvus 一致 |
| `ocr_model` | OCR 对话模型，默认 `qwen-vl-ocr-latest` |

环境变量前缀：`ALIYUN_`（如 `ALIYUN_API_KEY`）。

### 处理与日志

- `batch_size` / `max_workers`：批量并发与每批条数
- 日志：**控制台 + 文件**；API 默认 `logs/api.log`，批量默认 `logs/batch.log`，格式为 `时间 \| 级别 \| 模块:函数:行 - 消息`

## 注意事项

1. **限流**：控制 `max_workers` 与批次大小，避免 DashScope 限流
2. **断点续传**：进度文件 + `last_processed_id`，勿误删需续跑时的进度
3. **失败重试**：查看与进度同目录的 **`failed_records.jsonl`**
4. **Schema 变更**：Milvus 字段或维度变更后必须重建集合并全量重导

## 许可证

MIT License
