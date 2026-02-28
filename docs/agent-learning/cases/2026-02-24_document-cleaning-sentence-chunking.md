# 文档清洗 + 句子切分优化 - Agent Learning Case

> **填写日期**: 2026-02-24
> **工作类型**: document-cleaning + chunking
> **状态**: completed

---

## 1. 问题描述（Agent 需要识别什么？）

**原始输入**：
```
政策文档 Markdown（包含 PDF 解析后的原始内容）
```

**观察到的问题**：
- [ ] 问题 1：目录（TOC）被当作正文内容切分，生成无关 chunk
- [ ] 问题 2：英文句号 `.` 被误判为句子结束符，导致日期（如 2025.12.22）被错误切分
- [ ] 问题 3：列表编号（如 1.）与内容被分离到不同 chunk

**问题模式特征**（可量化）：
- 初始 chunk 数量：403 个
- 目录相关 chunk：约 36 个（9%）
- 日期被错误切分的实例：多个（如 "第十六周（ **2025." 被切断）

---

## 2. 尝试过的方案（Agent 的学习材料）

### 方案 1: 添加目录去除功能
**思路**：目录不是实际内容，属于导航信息，应在清洗阶段移除

**实现**：
```python
def _remove_toc(self, text: str) -> str:
    """检测并去除目录"""
    # 1. 识别目录标题：#### 目 录 或 ## 目录
    # 2. 识别目录项格式：
    #    - 数字 标题 ............（省略号格式）
    #    - 数字. 标题（点号格式）
    # 3. 连续多行目录项则判定为目录区域并移除
```

**结果**：
- ✅ 成功：目录被正确移除
- 📊 指标：chunk 数量从 403 降至 367

---

### 方案 2: 切换到 SentenceWindowNodeParser
**思路**：使用 LlamaIndex 的句子窗口切分器，支持 sentence-boundary-aware 切分

**实现**：
```python
from llama_index.core.node_parser.text.sentence_window import SentenceWindowNodeParser

return SentenceWindowNodeParser.from_defaults(
    sentence_splitter=split_by_regex(_SENTENCE_REGEX),
    window_size=3,
)
```

**结果**：
- ✅ 成功：每个 chunk 现在是完整句子
- 📊 指标：支持在 metadata 中存储周围句子作为上下文

---

### 方案 3: 仅使用中文句子结束符
**思路**：移除英文结束符，避免日期等被误切

**实现**：
```python
_SENTENCE_REGEX = (
    r'(?:^|\n)#{1,6}\s+[^\n]+'  # 标题行
    r'|'
    r'\d+[.\)）][^。！？；\n]*[。！？；]+'  # 列表项
    r'|'
    r'(?<!\d)[^。！？；\n]*[。！？；]+'  # 普通句子（仅中文结束符）
)
```

**结果**：
- ✅ 成功：日期 "2025.12.22-12.26" 不再被错误切分
- 📊 指标：chunk 数量从 367 降至 324

---

## 3. 最终方案（Agent 的策略库）

**核心策略**：政策文档清洗 + 句子窗口切分，使用中文结束符

**关键规则**：
1. 规则 1：清洗阶段移除目录（TOC）区域
2. 规则 2：切分时仅使用中文句子结束符（。！？；）
3. 规则 3：列表项（数字+点）保留完整，不切断
4. 规则 4：标题行作为独立 chunk

**代码实现**：
- 清洗逻辑：`services/ingestion/app/parsing/cleaner.py`
  - 方法：`_remove_toc()`
- 切分逻辑：`services/ingestion/app/components/chunkers/sentence.py`
  - 类：`SentenceChunker`
  - 正则：`_SENTENCE_REGEX`

**参数配置**：
```yaml
# sentence chunker
window_size: 3  # 周围 3 个句子作为上下文
sentence_terminators: ["。", "！？；"]  # 仅中文
```

---

## 4. 评估标准（Agent 的反思依据）

### 定量指标
| 指标 | 改进前 | 改进后 | 目标 |
|------|--------|--------|------|
| Chunk 数量 | 403 | 324 | <350 |
| 目录相关 chunk | ~36 (9%) | 0 | 0 |
| 日期错误切分 | 多个 | 0 | 0 |
| 平均 chunk 长度 | ~50 chars | ~60 chars | 50-100 |

### 定性检查
- [x] 目录已移除
- [x] 句子完整（无不必要拆分）
- [x] 日期保留完整
- [x] 列表项完整
- [x] 上下文窗口正确（window_size=3）

---

## 5. 适用场景（Agent 的匹配规则）

**文档特征**：
- 文档类型：政策文档、手册、论文指导
- 语言：中文为主
- 格式：Markdown（从 PDF 转换）
- 包含目录：通常是

**触发条件**：
```python
if (
    doc_type in ["policy", "manual", "guide"] and
    has_chinese_content and
    has_table_of_contents
):
    use_toc_removal = True
    use_sentence_chunker = True
```

---

## 6. 已知限制（Agent 的避坑指南）

- ⚠️ 限制 1：如文档使用英文结束符作为句子分隔，不适用此方案
- ⚠️ 限制 2：嵌套列表可能需要额外处理
- ⚠️ 限制 3：window_size 需要根据实际效果调整

---

## 7. 未来改进方向（Agent 的演化路径）

- [ ] 根据实际检索效果动态调整 window_size
- [ ] 添加语义切分作为备选方案
- [ ] 集成文档类型自动检测

---

## 8. 相关资源

- 清洗代码：`services/ingestion/app/parsing/cleaner.py`
- 切分代码：`services/ingestion/app/components/chunkers/sentence.py`
- 测试脚本：`services/ingestion/batch_test.py`
- 测试数据：`services/ingestion/data/parsed/policy/cleaned/`

---

## Agent 使用建议

**如果你是 AI Agent，看到这个案例时：**

1. **观察阶段**：检查文档是否包含目录、是否为中文政策文档
2. **规划阶段**：使用 TOC 去除 + 句子窗口切分策略
3. **执行阶段**：应用仅中文结束符的正则表达式
4. **反思阶段**：验证日期未被切分、列表项完整
5. **学习阶段**：如遇非中文文档，记录为新案例
