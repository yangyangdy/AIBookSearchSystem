# OCR文字存储与处理方案

## 一、问题分析

### 1.1 核心问题

1. **存储位置**：OCR提取的文字应该存在Milvus还是MySQL？
2. **文字内容**：封面图片可能包含多种文字（书名、作者、出版社、ISBN、推荐语等），如何处理？

### 1.2 实际情况

- 封面图片的OCR文字可能包含：
  - 书名（主要信息）
  - 作者名
  - 出版社
  - ISBN号
  - 价格
  - 推荐语/宣传语
  - 其他装饰性文字

- OCR文字长度可能：
  - 短文本：几十字（仅书名）
  - 中等文本：100-500字（书名+作者+出版社）
  - 长文本：500-2000字（包含推荐语、简介等）

---

## 二、存储方案对比

### 2.1 方案A：全部存在Milvus

**优点：**
- ✅ 检索时无需额外查询MySQL，性能好
- ✅ 数据集中存储，管理简单
- ✅ 支持在检索结果中直接返回OCR文字

**缺点：**
- ❌ Milvus的VARCHAR字段有长度限制（通常最大65535字节）
- ❌ 如果OCR文字很长，可能超出限制
- ❌ 占用Milvus存储空间，影响性能
- ❌ 不利于全文检索（Milvus不支持全文检索）

**适用场景：**
- OCR文字较短（< 2000字）
- 不需要全文检索
- 检索性能要求高

### 2.2 方案B：全部存在MySQL

**优点：**
- ✅ 无长度限制，支持长文本存储
- ✅ 支持全文检索（MySQL FULLTEXT索引）
- ✅ 不占用Milvus存储空间
- ✅ 便于后续分析和处理

**缺点：**
- ❌ 检索时需要额外查询MySQL，增加延迟
- ❌ 需要维护Milvus和MySQL的数据一致性
- ❌ 检索流程更复杂

**适用场景：**
- OCR文字较长（> 2000字）
- 需要全文检索功能
- 对检索延迟要求不高

### 2.3 方案C：混合存储（推荐）

**存储策略：**
- **Milvus存储**：关键信息（书名、作者等结构化信息）+ 摘要文字（前500字）
- **MySQL存储**：完整OCR文字

**优点：**
- ✅ 兼顾性能和灵活性
- ✅ Milvus存储关键信息，检索时直接获取
- ✅ MySQL存储完整文字，支持全文检索
- ✅ 避免Milvus字段长度限制

**缺点：**
- ⚠️ 需要维护两处数据的一致性
- ⚠️ 需要提取和结构化OCR文字

**适用场景：**
- **推荐方案**，适合大多数场景
- 兼顾检索性能和功能需求

---

## 三、推荐方案：混合存储 + 结构化处理

### 3.1 存储设计

#### Milvus存储（关键信息）

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `ocr_title` | VARCHAR(256) | 提取的书名 | 快速匹配 |
| `ocr_author` | VARCHAR(128) | 提取的作者 | 快速匹配 |
| `ocr_summary` | VARCHAR(500) | OCR文字摘要（前500字） | 二次过滤 |
| `ocr_keywords` | VARCHAR(200) | 提取的关键词 | 关键词过滤 |

#### MySQL存储（完整信息）

**表结构：**
```sql
CREATE TABLE book_ocr_text (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    mysql_id BIGINT NOT NULL COMMENT '关联book_info_table的id',
    milvus_id BIGINT COMMENT '关联Milvus的id',
    ocr_full_text TEXT COMMENT '完整OCR文字',
    ocr_title VARCHAR(256) COMMENT '提取的书名',
    ocr_author VARCHAR(128) COMMENT '提取的作者',
    ocr_publisher VARCHAR(128) COMMENT '提取的出版社',
    ocr_isbn VARCHAR(32) COMMENT '提取的ISBN',
    ocr_keywords VARCHAR(500) COMMENT '提取的关键词',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_mysql_id (mysql_id),
    INDEX idx_milvus_id (milvus_id),
    FULLTEXT INDEX ft_ocr_text (ocr_full_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3.2 OCR文字处理流程

```
OCR原始文字
    ↓
1. 文字清理（去除特殊字符、空格规范化）
    ↓
2. 结构化提取：
   ├─→ 书名提取（通过位置、字体大小、关键词识别）
   ├─→ 作者提取（"作者："、"著："等关键词）
   ├─→ 出版社提取（"出版社："、"出版："等关键词）
   ├─→ ISBN提取（正则匹配ISBN格式）
   └─→ 关键词提取（TF-IDF或简单分词）
    ↓
3. 生成摘要（前500字，去除无关文字）
    ↓
4. 存储：
   ├─→ Milvus：ocr_title, ocr_author, ocr_summary, ocr_keywords
   └─→ MySQL：完整文字 + 结构化字段
```

### 3.3 结构化提取策略

#### 策略1：基于规则提取（快速项目推荐）

**书名提取：**
- 识别封面中心或上方的文字（通常字体最大）
- 识别"书名："、"标题："等关键词后的文字
- 识别ISBN上方的文字（通常为书名）

**作者提取：**
- 识别"作者："、"著："、"编："等关键词后的文字
- 识别书名下方的文字（通常为作者）

**出版社提取：**
- 识别"出版社："、"出版："等关键词后的文字
- 识别封面底部的文字（通常为出版社）

**ISBN提取：**
- 正则匹配：`ISBN[\s:]*[\d\-X]+`
- 或匹配：`978[\d\-]+`（ISBN-13格式）

#### 策略2：基于AI提取（后续优化）

**使用大模型提取：**
- 调用通义千问等大模型
- 提示词："请从以下OCR文字中提取书名、作者、出版社、ISBN等信息"
- 返回结构化JSON

**优点：**
- 准确率高
- 能处理复杂格式

**缺点：**
- 需要额外API调用
- 增加处理时间和成本

### 3.4 关键词提取策略

**方法1：简单分词（快速项目）**
- 使用jieba等分词工具
- 提取名词和重要词汇
- 去除停用词

**方法2：TF-IDF（后续优化）**
- 计算词频和逆文档频率
- 提取重要关键词
- 更准确但计算量大

---

## 四、检索策略

### 4.1 向量检索 + OCR过滤流程

```
1. 向量相似度检索（Milvus）
   ↓
2. 获取Top-K结果（如Top-20）
   ↓
3. OCR文字过滤（可选）：
   ├─→ 方案A：使用Milvus中的ocr_summary进行关键词匹配
   ├─→ 方案B：查询MySQL进行全文检索
   └─→ 方案C：结合使用（先用Milvus过滤，再用MySQL精确匹配）
   ↓
4. 返回最终结果
```

### 4.2 OCR过滤方式

#### 方式1：关键词匹配（快速）

**使用Milvus中的ocr_summary：**
- 在检索结果中直接获取ocr_summary
- 使用Python进行关键词匹配
- 过滤包含关键词的结果

**优点：**
- 快速，无需查询MySQL
- 实现简单

**缺点：**
- 只能匹配摘要中的关键词
- 可能遗漏完整文字中的信息

#### 方式2：全文检索（精确）

**使用MySQL的FULLTEXT索引：**
- 获取检索结果的mysql_id列表
- 在MySQL中进行全文检索
- 返回匹配的结果

**优点：**
- 能匹配完整文字
- 支持模糊匹配

**缺点：**
- 需要额外查询MySQL
- 增加延迟

#### 方式3：混合过滤（推荐）

**两阶段过滤：**
1. **第一阶段**：使用Milvus中的ocr_summary进行快速过滤
2. **第二阶段**：对高相似度结果（>0.9），查询MySQL进行精确匹配

**优点：**
- 兼顾性能和准确性
- 减少MySQL查询次数

---

## 五、实施建议

### 5.1 快速项目方案（推荐）

**存储策略：**
- **Milvus**：存储ocr_summary（前500字）+ ocr_title + ocr_author
- **MySQL**：存储完整OCR文字（可选，如果文字较长）

**处理策略：**
- 使用基于规则的提取方法
- 简单分词提取关键词
- 检索时使用Milvus中的ocr_summary进行关键词匹配

**优点：**
- 实现简单，快速上线
- 性能好，无需额外查询MySQL
- 满足基本需求

### 5.2 完整方案（后续优化）

**存储策略：**
- **Milvus**：存储结构化信息（title, author, summary, keywords）
- **MySQL**：存储完整文字 + 结构化字段 + 全文索引

**处理策略：**
- 使用AI提取结构化信息（通义千问）
- TF-IDF提取关键词
- 检索时支持全文检索

**优点：**
- 功能完整
- 准确率高
- 支持复杂查询

---

## 六、Milvus Schema更新

### 6.1 更新后的Schema

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `id` | INT64 | 主键ID | 唯一标识 |
| `mysql_id` | INT64 | MySQL中的原始ID | 关联回MySQL |
| `sku` | VARCHAR(128) | 商品SKU | 业务标识 |
| `isbn` | VARCHAR(32) | ISBN号 | 业务标识 |
| `cover_link` | VARCHAR(512) | 图片链接 | 图片访问 |
| `cover_hash` | VARCHAR(16) | 感知哈希 | 快速去重 |
| `ocr_title` | VARCHAR(256) | 提取的书名 | 快速匹配 |
| `ocr_author` | VARCHAR(128) | 提取的作者 | 快速匹配 |
| `ocr_summary` | VARCHAR(500) | OCR文字摘要 | 关键词过滤 |
| `ocr_keywords` | VARCHAR(200) | 提取的关键词 | 关键词过滤 |
| `embedding` | FLOAT_VECTOR(768) | 图片向量 | 相似度检索 |

**注意：**
- 移除了`ocr_text`字段（完整文字存MySQL）
- 新增了结构化字段（ocr_title, ocr_author, ocr_summary, ocr_keywords）

---

## 七、总结

### 7.1 推荐方案

**存储：混合存储**
- Milvus：关键信息 + 摘要（用于快速过滤）
- MySQL：完整文字（用于全文检索）

**处理：结构化提取**
- 基于规则提取书名、作者、出版社、ISBN
- 生成摘要（前500字）
- 提取关键词

**检索：两阶段过滤**
- 第一阶段：向量相似度检索（Milvus）
- 第二阶段：OCR关键词过滤（使用Milvus中的ocr_summary）

### 7.2 实施优先级

**第一阶段（快速项目）：**
1. Milvus存储ocr_summary（前500字）
2. 简单规则提取书名、作者
3. 检索时使用ocr_summary进行关键词匹配

**第二阶段（后续优化）：**
1. 增加MySQL存储完整文字
2. 使用AI提取结构化信息
3. 支持全文检索
