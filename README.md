# 企业级多模态 Agentic RAG 微服务平台

基于 **LlamaIndex + LangGraph + Qdrant + MySQL** 构建的多模态检索增强生成系统，采用微服务架构。包含数据接入、推理服务、UI 网关三个独立服务，支持全维度消融实验与多模态文档处理（PDF 图文提取、VLM 摘要、角色过滤）。

## 架构概览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Ingestion  │     │  Inference  │     │   Gateway   │
│  Service    │     │  Service    │     │   Service   │
│  (Port 8001)│     │  (Port 8002)│     │  (Port 7860)│
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌───────────────────────┐  ┌────────────────────────────┐
│   Qdrant (Port 6333)  │  │     MySQL (Port 3306)      │
│ Vector DB (text+image)│  │ Parent Nodes (images+meta) │
└───────────────────────┘  └────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.11+
- Docker & Docker Compose
- 阿里云 DashScope API Key (Qwen-Plus, text-embedding-v4, Qwen-VL)

### 1. 一键启动 (推荐)

```bash
# 复制环境变量模板
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

# 启动全部服务
docker compose up -d
```

服务地址：
- Gateway UI: http://localhost:7860
- Ingestion API: http://localhost:8001
- Inference API: http://localhost:8002
- Qdrant Dashboard: http://localhost:6333/dashboard
- MySQL: localhost:3306 (rag_user/rag_password)

### 2. 本地开发

```bash
# 安装 shared 库
cd shared && poetry install

# 安装各服务依赖 (已在上一会话完成)
cd ../services/ingestion && poetry install
cd ../inference && poetry install
cd ../gateway && poetry install
cd ../../cli && poetry install

# 启动 Qdrant
docker run -p 6333:6333 qdrant/qdrant

# 启动各服务 (各终端分别运行)
cd services/ingestion && poetry run python -m app.main
cd services/inference && poetry run python -m app.main
cd services/gateway && poetry run python -m app.main
```

## 项目结构

```
my_rag_project/
├── shared/                          # 共享库 (零重型依赖)
│   └── rag_shared/
│       ├── core/types.py            # 抽象基类 (8 types, incl. multimodal)
│       ├── core/registry.py         # 组件注册中心 (8 component types)
│       ├── config/experiment.py     # 实验配置 (含多模态字段)
│       ├── schemas/                 # Pydantic 模型
│       │   ├── ingestion.py
│       │   ├── inference.py
│       │   └── multimodal.py       # 多模态数据模型
│       └── utils/
│           ├── logger.py
│           └── role_mapper.py       # 角色自动提取
│
├── services/
│   ├── ingestion/                   # 数据接入服务 (Port 8001)
│   │   └── app/
│   │       ├── api/routes.py        # REST API (含 upload-multimodal)
│   │       ├── services/ingestion.py  # 层级节点处理
│   │       ├── storage/vectordb.py  # Named Vectors 支持
│   │       ├── components/
│   │       │   ├── chunkers/        # fixed, recursive, sentence, semantic, multimodal
│   │       │   ├── providers/       # dashscope, bgem3, vlm (Qwen-VL)
│   │       │   └── processors/     # 图片压缩与去重
│   │       └── parsing/            # PDF/DOCX 解析 + 多模态 PDF 提取
│   │
│   ├── inference/                   # 推理服务 (Port 8002)
│   │   └── app/
│   │       ├── api/routes.py        # SSE 流式 API
│   │       ├── agent/               # LangGraph 工作流
│   │       ├── services/
│   │       │   ├── retrieval.py     # 文本检索
│   │       │   └── multimodal_retrieval.py  # 图文检索
│   │       ├── storage/
│   │       │   ├── vectordb.py
│   │       │   └── mysql_client.py  # 父节点查询
│   │       └── components/providers/  # dashscope, bgem3, qwen_vl_llm
│   │
│   └── gateway/                     # UI 网关 (Port 7860)
│       └── app/
│           ├── clients/             # HTTP 客户端
│           └── ui/app.py            # Gradio 界面
│
├── cli/                             # CLI 评测工具
│   └── rag_cli/main.py             # rag-eval 命令
│
├── configs/
│   ├── default.yaml                 # 单实验配置
│   ├── ablation_grid.yaml           # 消融实验矩阵
│   └── hierarchical_markdown.yaml   # 层级 Markdown 切分配置
│
├── scripts/
│   └── init_mysql.sql               # MySQL 初始化脚本
│
├── data/                            # 运行时数据 (gitignored)
│   ├── vectordb/                    # Qdrant 数据
│   ├── mysql/                       # MySQL 数据
│   ├── metadata.db                  # SQLite 元数据
│   └── uploads/                     # 文件上传
│
├── docs/                            # 文档
│   └── agent-learning/              # Agent 学习案例
│
├── docker-compose.yml               # 容器编排 (含 MySQL)
├── .env.example                     # 环境变量模板
├── CLAUDE.md                        # Claude Code 指南
└── README.md                        # 本文档
```

## 服务说明

### Ingestion Service (8001)

负责文档解析、切片、向量化、存储。支持多模态 PDF 图文提取与层级节点管理。

**API 端点：**
- `POST /api/v1/documents/upload` - 上传并入库文件（支持层级节点输出）
- `POST /api/v1/documents/upload-multimodal` - 上传 PDF 并提取图文对（PyMuPDF）
- `POST /api/v1/documents/ingest` - 从路径入库
- `POST /api/v1/batch/ingest` - 批量智能入库
- `GET /api/v1/collections` - 列出 collections
- `GET /api/v1/collections/{name}/files` - 列出文件
- `DELETE /api/v1/documents/{collection}/{filename}` - 删除文档

### Inference Service (8002)

负责查询、LangGraph Agent 推理、SSE 流式输出。支持多模态检索（图文混合搜索）。

**API 端点：**
- `POST /api/v1/chat/stream` - SSE 流式对话
- `POST /api/v1/chat/reset` - 重置对话
- `POST /api/v1/retrieval/search` - 直接检索
- `POST /api/v1/evaluate/single` - 单配置评测

### Gateway Service (7860)

Gradio UI 界面，通过 HTTP 代理调用后端服务。

## CLI 评测工具

```bash
cd cli

# 单配置评测
poetry run rag-eval --config ../configs/default.yaml --limit 10

# 消融矩阵评测
poetry run rag-eval --grid ../configs/ablation_grid.yaml --limit 10

# 批量入库
poetry run rag-eval --ingest --input-dir ../data/uploads/documents
```

## 切片策略

| 策略 | 实现 | 描述 |
|------|------|------|
| `fixed` | TokenTextSplitter | 按 Token 数硬切 |
| `recursive` | RecursiveCharacterTextSplitter | 按中文标点层级递归 |
| `sentence` | SentenceSplitter | 句子边界感知 |
| `semantic` | SemanticSplitterNodeParser | 基于 Embedding 语义切分 |
| `multimodal` | MultimodalChunker | 图文对提取，VLM 摘要，层级父子节点 |

## 扩展指南

### 添加新的切片策略

在对应服务的 `components/chunkers/` 目录实现，继承 `BaseChunker`，使用 `@ComponentRegistry.chunker("name")` 注册。

### 添加新的模型供应商

在 `components/providers/` 目录实现 `BaseLLMProvider` / `BaseEmbeddingProvider` / `BaseRerankerProvider` 接口。

## 技术栈

| 组件 | 技术 |
|------|------|
| LLM / Embedding | 阿里云 DashScope (Qwen-Plus, text-embedding-v4) |
| VLM (视觉语言模型) | 阿里云 DashScope (Qwen-VL-Max, qwen3-vl-embedding) |
| 稀疏向量 | jieba 中文分词 + MD5 哈希 |
| 向量数据库 | Qdrant (Named Vectors: text + image) |
| 关系数据库 | MySQL 8.0 (父节点 + 图片存储) |
| Agent 工作流 | LangGraph (ReAct + Map-Reduce) |
| 检索框架 | LlamaIndex |
| PDF 图文提取 | PyMuPDF + Pillow |
| 前端 | Gradio 5.0 |
| 依赖管理 | Poetry (各服务独立环境) |

## 多模态架构

### 层级节点存储

多模态文档采用 **父子节点分离存储** 策略：

- **父节点** (Parent) → MySQL：包含完整图片 (base64) + 上下文文本 + 元数据
- **子节点** (Child) → Qdrant：图片的 VLM 文本摘要，用于向量检索
- 检索时通过子节点找到父节点，再用 VLM 基于原始图片生成回答

### 角色过滤

系统自动从中文文件名提取用户角色（指导老师、学生、评阅专家、答辩组），在检索时按角色过滤内容。

## 注意事项

- **numpy 版本隔离**: Ingestion (>=2.0), Inference (<2.0)
- **共享库**: `shared/rag_shared/` 作为 path dependency 供各服务使用
- **运行时数据**: 保存在 `data/` 目录 (gitignored)，包含 `vectordb/`、`mysql/`、`metadata.db`、`uploads/`
- **稀疏向量**: 约 15MB，启动秒级完成
- **多模态指纹**: `enable_multimodal=True` 时，`ingestion_fingerprint` 包含多模态参数，确保独立集合
- **MySQL 初始化**: `scripts/init_mysql.sql` 由 Docker Compose 自动执行
