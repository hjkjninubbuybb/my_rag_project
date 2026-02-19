# 企业级 Agentic RAG 消融实验平台

基于 **LlamaIndex + LangGraph + Qdrant** 构建的检索增强生成系统，支持全维度消融实验（Ablation Study）。采用 **注册中心 + 抽象基类** 架构，实现切片策略、模型供应商、检索管线的动态插拔与组合实验。

## 核心特性

- **全维度消融实验**：切片策略 x 切片参数 x 混合检索 x 重排序，笛卡尔积自动生成所有实验组合
- **智能入库**：相同入库指纹（切片+Embedding）的实验共享 Qdrant Collection，避免重复入库
- **开闭原则**：新增切片策略或模型供应商只需实现接口 + 注册装饰器，无需修改现有代码
- **中文友好切片**：三种差异化切片策略（固定 Token / 递归分隔符 / 句子边界），均针对中文标点优化
- **Agent 调试透视**：基于 Tool Artifact 的无侵入式检索数据拦截，前端可获取物理分块原文、Score、来源文件
- **5-Tab Gradio UI**：实验配置 → 批量运行 → 结果看板 → 交互对话 → 知识库管理
- **评测指标**：Hit Rate / MRR / NDCG，语义判定 + 子串匹配双重命中检测

## 技术栈

| 组件 | 技术 |
|------|------|
| LLM / Embedding / Reranker | 阿里云 DashScope (Qwen-Plus, text-embedding-v4, GTE-Rerank) |
| 稀疏向量 | jieba 中文分词 + 哈希稀疏向量 |
| 向量数据库 | Qdrant (本地模式) |
| 元数据存储 | SQLite |
| Agent 工作流 | LangGraph (ReAct + Map-Reduce) |
| 检索框架 | LlamaIndex |
| 前端 | Gradio 5.0 |
| 配置管理 | Pydantic Settings + YAML |
| 依赖管理 | Poetry |

## 项目结构

```
my_rag_project/
├── configs/                          # 实验配置
│   ├── default.yaml                  # 默认单实验配置
│   └── ablation_grid.yaml            # 消融实验矩阵
│
├── src/rag/                          # 主包
│   ├── main.py                       # 程序入口
│   ├── config/                       # 配置管理
│   │   ├── settings.py               # 全局设置 (Pydantic BaseSettings)
│   │   └── experiment.py             # ExperimentConfig + ExperimentGrid
│   ├── core/                         # 核心抽象
│   │   ├── types.py                  # 抽象基类 (BaseChunker, BaseLLMProvider 等)
│   │   └── registry.py              # ComponentRegistry 注册中心
│   ├── components/                   # 可插拔组件实现
│   │   ├── chunkers/                 # fixed / recursive / sentence
│   │   └── providers/                # dashscope (LLM/Embedding/Reranker) + bgem3
│   ├── pipeline/                     # 数据处理流水线
│   │   ├── ingestion.py              # 入库服务 (文件→切片→向量化→Qdrant)
│   │   └── retrieval.py              # 检索服务 (Hybrid + Rerank + Debug Tool)
│   ├── storage/                      # 持久化存储
│   │   ├── vectordb.py               # Qdrant 管理器
│   │   └── metadata.py               # SQLite 文件元数据
│   ├── agent/                        # LangGraph 工作流
│   │   ├── workflow.py               # 主图 + ReAct 子图
│   │   ├── state.py                  # State / AgentState (含 debug_retrieved_chunks)
│   │   ├── nodes.py                  # 图节点 (含 ToolMessage artifact 收集)
│   │   ├── tools.py                  # 工具工厂 (debug-enabled)
│   │   └── prompts.py                # 系统提示词
│   ├── experiment/                   # 实验管理
│   │   ├── runner.py                 # 批量实验执行器
│   │   └── results.py                # 结果收集与持久化
│   └── ui/                           # Gradio 界面 (5 Tab)
│       └── app.py
│
├── scripts/                          # 工具脚本
│   ├── evaluate_retrieval.py         # 检索评测 (支持单配置/矩阵模式)
│   ├── diagnose_env.py               # 环境诊断
│   └── probe_qdrant.py               # Qdrant 数据探查
│
├── tests/
│   └── data/
│       └── test_dataset.csv          # 评测数据集
│
├── data/                             # 运行时数据 (gitignored)
│   ├── vectordb/                     # Qdrant 向量数据
│   ├── metadata.db                   # SQLite 元数据
│   ├── uploads/temp_batch/           # 文件上传暂存
│   └── reports/                      # 实验报告
│
├── resources/                        # 模型权重缓存 (gitignored)
├── .env                              # 环境变量 (gitignored)
├── .env.example                      # 环境变量模板
└── pyproject.toml                    # 依赖管理
```

## 快速开始

### 1. 安装依赖

```bash
poetry install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入阿里云 DashScope API Key
```

### 3. 启动系统

```bash
python src/rag/main.py
```

浏览器自动打开 `http://127.0.0.1:7860`，通过 Gradio UI 进行操作。

指定配置文件和端口：

```bash
python src/rag/main.py --config configs/default.yaml --port 8080
```

## 切片策略

三种差异化切片策略，均针对中文文本优化：

| 策略 | 实现 | 切分方式 | 适用场景 |
|------|------|---------|---------|
| `fixed` | LlamaIndex `TokenTextSplitter` | 按 Token 数硬切，不关心语义边界 | Baseline 对照组 |
| `recursive` | LangChain `RecursiveCharacterTextSplitter` | 按中文标点层级递归回退：段落→句号→问号→感叹号→分号→逗号→空格→逐字符 | 结构化文档 |
| `sentence` | LlamaIndex `SentenceSplitter` + 中文正则 | 句子边界感知，增强中文标点（。？！，、；：）识别 | 连续文本 |

## 消融实验

### 通过 UI 操作

1. 在 **知识库管理** Tab 上传文档，点击"确认上传"
2. 打开 **实验配置** Tab，选择各维度参数，点击"预览组合"
3. 切换到 **运行实验** Tab，先"智能入库"再"运行评测"
4. 在 **结果看板** Tab 查看对比表和可视化图表

### 通过命令行

```bash
# 单配置评测
python scripts/evaluate_retrieval.py --config configs/default.yaml --limit 10

# 消融矩阵评测（笛卡尔积全组合）
python scripts/evaluate_retrieval.py --grid configs/ablation_grid.yaml --limit 10

# 默认 4 组检索消融（Baseline / No Hybrid / No Rerank / Full）
python scripts/evaluate_retrieval.py --limit 10
```

### 消融矩阵配置示例

编辑 `configs/ablation_grid.yaml`：

```yaml
grid:
  chunking_strategies: ["fixed", "recursive", "sentence"]
  chunk_sizes_child: [128, 256, 512]
  chunk_overlaps: [25, 50]
  enable_hybrid: [true, false]
  enable_auto_merge: [true, false]
  enable_rerank: [true, false]
```

以上配置将生成 3 x 3 x 2 x 2 x 2 x 2 = **144** 个实验组合。

### 评测指标

| 指标 | 含义 |
|------|------|
| Hit Rate | 命中率，Top-K 结果中是否包含正确答案 |
| MRR | 平均倒数排名，第一个正确结果的排名倒数 |
| NDCG@K | 归一化折损累积增益，综合评估排序质量 |

命中检测采用双重机制：子串匹配（快速通道）+ 余弦相似度 > 0.85（语义兜底）。

## 扩展指南

### 添加新的切片策略

```python
# src/rag/components/chunkers/semantic.py
from rag.core.registry import ComponentRegistry
from rag.core.types import BaseChunker

@ComponentRegistry.chunker("semantic")
class SemanticChunker(BaseChunker):
    def create_splitter(self, chunk_size, chunk_overlap):
        # 实现你的语义切片逻辑
        ...
```

在 `components/chunkers/__init__.py` 中添加导入，YAML 配置中即可使用 `chunking_strategy: "semantic"`。

### 添加新的模型供应商

```python
# src/rag/components/providers/openai.py
from rag.core.registry import ComponentRegistry
from rag.core.types import BaseLLMProvider

@ComponentRegistry.llm_provider("openai")
class OpenAILLMProvider(BaseLLMProvider):
    def create_llm(self, model_name, api_key, temperature, **kwargs):
        # 返回 LlamaIndex LLM（用于检索管线）
        ...

    def create_chat_model(self, model_name, api_key, temperature, **kwargs):
        # 返回 LangChain ChatModel（用于 Agent 工作流）
        ...
```

YAML 中配置 `llm_provider: "openai"` 即可切换，检索管线和 Agent 工作流自动使用对应供应商。

## 架构设计

### 检索管线

```
Query → [Hybrid Search: Dense + jieba Sparse] → [Rerank: GTE] → Top-K
```

每个环节均可通过 `ExperimentConfig` 独立开关控制，支持任意组合的消融实验。

### Agent 工作流

```
用户问题 → 对话总结 → 问题分析/拆分 → [并行 ReAct Agent x N] → 聚合回答
```

- **问题分析**：LLM 判断是否需要将复杂问题拆分为多个子问题，简单问题直通
- **并行检索**：每个子问题独立执行 ReAct 循环（搜索→分析→回答）
- **智能聚合**：单问题直接返回（无额外 LLM 开销），多问题 LLM 整合为连贯回答
- **LLM 解耦**：通过注册中心按 `llm_provider` 动态创建，支持供应商热切换

### Agent 调试数据拦截

```
Custom Tool (query_engine.query())
  → 返回 (str_response, debug_chunks) 给 ToolNode
  → ToolMessage.artifact 存储 debug_chunks
  → extract_final_answer 收集所有 artifact
  → State.debug_retrieved_chunks (operator.add Reducer 累加)
  → graph.ainvoke() 返回值中包含完整检索链路数据
```

debug_chunks 结构：`[{"text": "...", "score": 0.87, "source_file": "report.pdf"}, ...]`

### 依赖注入

所有服务组件（`IngestionService`、`RetrievalService`、`VectorStoreManager`、`create_graph`）接收 `ExperimentConfig` 参数，不依赖全局单例。同一进程可同时运行多个不同配置的实验。

### 智能入库机制

`ExperimentConfig.ingestion_fingerprint` 由切片参数 + Embedding 模型计算 MD5 得出。相同 fingerprint 的实验共享 Qdrant Collection，仅检索参数不同的实验无需重复入库。

## 注意事项

- 稀疏向量使用 jieba 中文分词（约 15MB），启动秒级完成，无需下载大模型
- 旧版 `metadata.db` 如缺少 `collection_name` 字段，需删除后重建
- 如从旧版（BGE-M3）迁移，需删除 `data/vectordb/` 后重新入库（稀疏向量索引空间不兼容）
