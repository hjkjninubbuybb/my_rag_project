# Agent Learning Materials（Agent 学习材料库）

## 目的

记录**传统方法**工作中的经验、问题、解决方案，为未来的 Agent 化提供：
1. **问题识别模式**（Agent 的"观察"能力）
2. **解决方案库**（Agent 的"策略"知识）
3. **评估标准**（Agent 的"反思"依据）
4. **失败案例**（Agent 的"避坑"指南）

## 记录原则

- ✅ 记录**思考过程**，而不只是最终代码
- ✅ 记录**为什么这样做**，而不只是做了什么
- ✅ 记录**失败尝试**，而不只是成功方案
- ✅ 记录**评估标准**，而不只是主观感觉

## 目录结构

```
docs/agent-learning/
├── README.md                           # 本文件
├── cases/                              # 具体案例（按时间命名）
│   ├── 2026-02-24_document-cleaning-policy.md
│   ├── 2026-02-25_query-rewriting-ambiguous.md
│   └── ...
├── patterns/                           # 提取的通用模式
│   ├── broken-paragraph-detection.md
│   ├── smart-spacing-for-chunking.md
│   └── ...
└── metrics/                            # 评估指标定义
    ├── chunking-quality.md
    └── information-retention.md
```

## 案例模板

见 `cases/TEMPLATE.md`

## 如何使用这些材料？

### 传统方法阶段（现在）
- 每次完成一个工作，填写一份案例记录
- 定期回顾，提取通用模式

### Agent 化阶段（未来）
- Agent 读取 `cases/` 作为示例学习
- Agent 读取 `patterns/` 作为策略库
- Agent 读取 `metrics/` 作为评估标准
- 新问题优先查询相似案例（RAG over cases）

## 统计

- 总案例数：1
- 总模式数：0
- 覆盖场景：document-cleaning
