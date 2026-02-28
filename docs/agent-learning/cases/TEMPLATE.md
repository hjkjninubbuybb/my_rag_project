# [工作名称] - Agent Learning Case

> **填写日期**: YYYY-MM-DD
> **工作类型**: [document-cleaning | query-rewriting | retrieval | chunking | ...]
> **状态**: [in-progress | completed | failed]

---

## 1. 问题描述（Agent 需要识别什么？）

**原始输入**：
```
[例如：PDF 解析后的 Raw Markdown]
```

**观察到的问题**：
- [ ] 问题 1：[例如：段落被拆分成多行]
- [ ] 问题 2：[例如：大量空行]
- [ ] ...

**问题模式特征**（可量化）：
- 指标 1: [例如：Single newlines: 69, Double newlines: 79]
- 指标 2: [例如：Average line length: 45 chars]

---

## 2. 尝试过的方案（Agent 的学习材料）

### 方案 1: [方案名称]
**思路**：[为什么尝试这个方案]

**实现**：
```python
# 关键代码片段
```

**结果**：
- ✅ 成功：[做对了什么]
- ❌ 失败：[有什么问题]
- 📊 指标：[compression: 3.4%, chunking_quality: 0.65]

---

### 方案 2: [方案名称]
...

---

## 3. 最终方案（Agent 的策略库）

**核心策略**：[一句话总结]

**关键规则**：
1. 规则 1：[例如：标题后添加空行]
2. 规则 2：[例如：列表项之间不添加空行]
3. ...

**代码实现**：
- 文件位置：`services/ingestion/app/parsing/cleaner.py`
- 关键方法：`_merge_paragraphs()`, `_is_list_item()`

**参数配置**：
```yaml
# 如果有可调参数
chunk_size: 500
quality_threshold: 0.8
```

---

## 4. 评估标准（Agent 的反思依据）

### 定量指标
| 指标 | 改进前 | 改进后 | 目标 |
|------|--------|--------|------|
| Compression Rate | 3% | 8.7% | >8% |
| Chunking Quality | N/A | 0.85 | >0.8 |
| Single Newlines | 69 | 16 | <30 |
| Double Newlines | 79 | 11 | 适度 |

### 定性检查
- [x] 段落完整（无不必要拆分）
- [x] 列表紧凑（同一列表在一个 chunk）
- [x] 关键信息保留（数字、标点完整）
- [x] Chunking 友好（有清晰的 \n\n 分隔符）

---

## 5. 适用场景（Agent 的匹配规则）

**文档特征**：
- 文档类型：[policy | manual | report | ...]
- 平均行长：[30-50 chars]
- 换行模式：[dense | sparse]
- 是否有列表：[是]

**触发条件**：
```python
if (
    doc_type == "policy" and
    avg_line_length < 60 and
    double_newline_ratio > 0.3
):
    use_this_strategy()
```

---

## 6. 已知限制（Agent 的避坑指南）

- ⚠️ 限制 1：[例如：如果列表项中有子列表，可能识别错误]
- ⚠️ 限制 2：[例如：表格内容暂未处理]

---

## 7. 未来改进方向（Agent 的演化路径）

- [ ] 改进 1：[例如：自动识别表格并保留格式]
- [ ] 改进 2：[例如：根据 chunking 效果动态调整空行策略]

---

## 8. 相关资源

- 实现代码：`services/ingestion/app/parsing/cleaner.py`
- 测试脚本：`services/ingestion/test_parsing_by_category.py`
- 可视化工具：`services/ingestion/visualize_newlines.py`
- 测试数据：`services/ingestion/data/policy/`

---

## Agent 使用建议

**如果你是 AI Agent，看到这个案例时：**

1. **观察阶段**：检查新文档是否匹配"适用场景"
2. **规划阶段**：如果匹配，使用"最终方案"中的策略
3. **执行阶段**：应用"关键规则"
4. **反思阶段**：用"评估标准"检查质量
5. **学习阶段**：如果失败，记录到"已知限制"；如果发现新问题，创建新案例
