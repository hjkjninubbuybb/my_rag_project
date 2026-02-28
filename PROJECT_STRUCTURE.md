# 项目结构总览（v3.0）

## 根目录结构

```
my_rag_project/
├── services/                    # 微服务目录
│   ├── indexing/               # Indexing Service (Port 8001)
│   ├── agent/                  # Agent Service (Port 8002)
│   ├── orchestrator/           # Orchestrator Service (Port 8000)
│   ├── testing/                # Testing Service (Port 8003)
│   └── mineru-parser/          # MinerU 解析器（独立工具）
│
├── scripts/                     # 运维脚本
│   ├── init_mysql.sql          # MySQL 初始化
│   ├── verify_infrastructure.sh # 基础设施验证
│   └── migrate_multimodal_schema.sql
│
├── configs/                     # 配置文件
│   ├── default.yaml
│   ├── ablation_grid.yaml
│   └── hierarchical_markdown.yaml
│
├── docs/                        # 文档目录
│   ├── refactoring-plan.md     # 重构计划
│   ├── agent-learning/         # Agent 学习材料
│   └── multimodal-*.md         # 多模态文档
│
├── data/                        # 运行时数据（gitignored）
│   ├── vectordb/               # Qdrant 本地存储
│   ├── mysql/                  # MySQL 数据目录
│   ├── reports/                # 评测报告
│   └── uploads/                # 用户上传文件
│
├── docker-compose.yml           # Docker Compose 配置
├── .env.example                 # 环境变量模板
├── CLAUDE.md                    # Claude Code 指南
├── README.md                    # 项目说明
├── REFACTORING_STATUS.md        # 重构状态
├── REFACTORING_COMPLETE.md      # 重构完成总结
└── PHASE6_CLEANUP_REPORT.md     # 清理报告
```

---

## 微服务详细结构

### 1. Indexing Service (Port 8001)

```
services/indexing/
├── app/
│   ├── api/
│   │   └── routes.py           # 8 个 API 端点
│   ├── core/
│   │   ├── types.py            # ABCs (8 个基类)
│   │   └── registry.py         # ComponentRegistry
│   ├── config/
│   │   └── experiment.py       # ExperimentConfig
│   ├── services/
│   │   ├── ingestion.py        # 入库服务
│   │   ├── retrieval.py        # 检索服务
│   │   └── multimodal_retrieval.py
│   ├── storage/
│   │   ├── vectordb.py         # Qdrant 客户端
│   │   ├── mysql_client.py     # MySQL 客户端
│   │   └── minio_client.py     # MinIO 客户端
│   ├── components/
│   │   ├── chunkers/           # 5 种切片器
│   │   ├── providers/          # Embedding/Reranker
│   │   └── processors/         # 图像处理
│   ├── parsing/
│   │   ├── parser.py           # 文档解析
│   │   ├── multimodal_parser.py
│   │   └── cleaner.py          # PolicyCleaner
│   ├── utils/
│   │   ├── logger.py
│   │   └── role_mapper.py
│   ├── config.py               # ServiceSettings
│   ├── main.py                 # FastAPI 应用
│   └── schemas.py              # Pydantic models
├── pyproject.toml              # Poetry 配置 (numpy>=2.0)
├── Dockerfile
├── README.md
├── IMPLEMENTATION.md
└── .env.example
```

**职责**: 解析、切片、Embedding、向量读写、Reranker

**关键特性**:
- 5 种切片策略（fixed, recursive, sentence, semantic, multimodal）
- 混合检索（Dense + Sparse + Reranking）
- 角色过滤（Chinese filename-based）
- MinIO 文件存储
- VLM 集成（调用 Agent Service）

---

### 2. Agent Service (Port 8002)

```
services/agent/
├── app/
│   ├── agent/
│   │   ├── workflow.py         # LangGraph 主图 + 子图
│   │   ├── state.py            # State + AgentState
│   │   ├── nodes.py            # 5 个节点
│   │   ├── tools.py            # knowledge_base_search
│   │   └── prompts.py          # System prompts
│   ├── api/
│   │   └── routes.py           # 5 个 API 端点
│   ├── services/
│   │   └── vlm.py              # VLM 分析服务
│   ├── components/
│   │   └── providers/
│   │       ├── dashscope_llm.py
│   │       └── qwen_vl.py
│   ├── utils/
│   │   └── logger.py
│   ├── config.py               # ServiceSettings
│   ├── main.py                 # FastAPI 应用
│   └── schemas.py              # Pydantic models
├── pyproject.toml              # Poetry 配置 (numpy<2.0)
├── Dockerfile
├── README.md
├── QUICKSTART.md
├── IMPLEMENTATION.md
└── VERIFICATION.md
```

**职责**: LLM 对话、VLM 分析、ReAct 工作流、SSE 流式输出

**关键特性**:
- LangGraph ReAct 工作流（5 节点）
- SSE 流式输出（token, rewrite, chunks, done, error）
- VLM 服务（DashScope Qwen-VL）
- HTTP 调用 Indexing Service（无直接 DB 访问）
- MemorySaver checkpointer

---

### 3. Orchestrator Service (Port 8000)

```
services/orchestrator/
├── app/
│   ├── api/
│   │   └── routes.py           # 5 个 API 端点
│   ├── services/
│   │   ├── indexing_client.py  # Indexing Service 客户端
│   │   ├── agent_client.py     # Agent Service 客户端
│   │   └── minio_client.py     # MinIO 客户端
│   ├── utils/
│   │   └── logger.py
│   ├── config.py               # ServiceSettings
│   ├── main.py                 # FastAPI 应用
│   └── schemas.py              # Pydantic models
├── pyproject.toml              # Poetry 配置
├── Dockerfile
├── README.md
├── QUICKSTART.md
├── IMPLEMENTATION.md
└── CHECKLIST.md
```

**职责**: 用户入口、文件上传到 MinIO、编排 Indexing + Agent

**关键特性**:
- 纯编排，无业务逻辑
- Lazy client 初始化
- SSE 流式代理
- MinIO 自动创建 buckets
- 端到端流程（上传 + 入库 + 对话）

---

### 4. Testing Service (Port 8003)

```
services/testing/
├── app/
│   ├── api/
│   │   └── routes.py           # 5 个 API 端点
│   ├── tests/
│   │   ├── test_indexing.py    # Indexing Service 测试
│   │   ├── test_agent.py       # Agent Service 测试
│   │   ├── test_orchestrator.py
│   │   └── test_e2e.py         # 端到端测试
│   ├── services/
│   │   ├── test_runner.py      # 测试执行器
│   │   └── result_storage.py   # 结果存储
│   ├── data/
│   │   ├── test_documents/     # 测试文档
│   │   └── test_queries.json   # 测试查询
│   ├── utils/
│   │   └── logger.py
│   ├── config.py               # ServiceSettings
│   ├── main.py                 # FastAPI 应用
│   └── schemas.py              # Pydantic models
├── pyproject.toml              # Poetry 配置
├── Dockerfile
├── README.md
├── TESTING_GUIDE.md
└── IMPLEMENTATION_SUMMARY.md
```

**职责**: 集中测试管理、测试数据、结果存储

**关键特性**:
- 4 个测试套件（indexing, agent, orchestrator, e2e）
- pytest + JSON 报告
- 结果持久化（MySQL test_runs 表）
- Lazy MySQL 初始化
- 独立测试数据

---

## 外部存储

### Qdrant (Port 6333)
- **用途**: 向量数据库
- **存储**: 文本向量（1536-dim）、稀疏向量（jieba）、图像向量（2560-dim）
- **访问者**: Indexing Service

### MySQL (Port 3306)
- **用途**: 关系数据库
- **表**:
  - `parent_nodes` - 多模态父节点
  - `collections` - Collection 元数据
  - `documents` - 文档元数据
  - `test_runs` - 测试运行记录
- **访问者**: Indexing Service, Testing Service

### MinIO (Port 9000, 9001)
- **用途**: 对象存储
- **Buckets**:
  - `raw-documents` - 原始 PDF 文件
  - `extracted-images` - 提取的图片
- **访问者**: Orchestrator Service, Indexing Service

---

## 服务依赖关系

```
┌──────────────────────────────────────────────────────────┐
│                    External Storage                       │
├──────────────────────────────────────────────────────────┤
│  Qdrant (6333)  │  MySQL (3306)  │  MinIO (9000)        │
└────────┬─────────┴────────┬───────┴──────────┬───────────┘
         │                  │                  │
         │                  │                  │
┌────────┴──────────────────┴──────────────────┴───────────┐
│                    Microservices Layer                    │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────┐                                     │
│  │  Orchestrator   │  Port 8000 (用户入口)                │
│  └────────┬────────┘                                     │
│           │                                               │
│      ┌────┴────┐                                         │
│      ▼         ▼                                         │
│  ┌─────────┐ ┌─────────┐                                │
│  │Indexing │←→│ Agent   │                                │
│  │  8001   │  │  8002   │                                │
│  └─────────┘  └─────────┘                                │
│                                                           │
│  ┌─────────┐                                             │
│  │ Testing │  Port 8003 (测试管理)                        │
│  └─────────┘                                             │
│                                                           │
└──────────────────────────────────────────────────────────┘

双向调用（不同流程，无循环）:
- 入库流程: Indexing → Agent /api/v1/vlm/analyze (VLM 摘要)
- 查询流程: Agent → Indexing /api/v1/retrieve (检索)
```

---

## 端口分配

| 服务 | 端口 | 用途 |
|------|------|------|
| Orchestrator | 8000 | 用户入口、流程编排 |
| Indexing | 8001 | 解析、切片、向量化、检索 |
| Agent | 8002 | LLM/VLM 推理、ReAct 工作流 |
| Testing | 8003 | 集中测试管理 |
| Qdrant | 6333, 6334 | 向量数据库 |
| MySQL | 3306 | 关系数据库 |
| MinIO | 9000, 9001 | 对象存储 |

---

## 配置文件

### Docker Compose
- `docker-compose.yml` - 完整服务编排（7 个容器）

### 环境变量
- `.env.example` - 环境变量模板
- 各服务 `.env.example` - 服务专用配置

### 数据库
- `scripts/init_mysql.sql` - MySQL 初始化（4 张表）
- `scripts/migrate_multimodal_schema.sql` - Schema 迁移

### 实验配置
- `configs/default.yaml` - 默认配置
- `configs/ablation_grid.yaml` - 消融实验
- `configs/hierarchical_markdown.yaml` - 层级切分

---

## 文档体系

### 项目级文档
- `README.md` - 项目说明
- `CLAUDE.md` - Claude Code 指南（架构文档）
- `REFACTORING_STATUS.md` - 重构状态跟踪
- `REFACTORING_COMPLETE.md` - 重构完成总结
- `PHASE6_CLEANUP_REPORT.md` - 清理报告
- `PROJECT_STRUCTURE.md` - 本文档

### 服务级文档
- 每个服务都有 `README.md`
- 部分服务有 `QUICKSTART.md`, `IMPLEMENTATION.md`, `VERIFICATION.md`

### 技术文档
- `docs/refactoring-plan.md` - 完整重构计划
- `docs/multimodal-*.md` - 多模态架构文档
- `docs/agent-learning/` - Agent 学习材料

---

## 代码统计

### 总体统计
- **服务数量**: 4 个微服务
- **代码行数**: ~5039 行
- **文件数量**: ~74 个
- **共享库**: 0 个

### 服务代码分布
```
Indexing:     2000 行 (40%)
Agent:        1500 行 (30%)
Orchestrator:  739 行 (15%)
Testing:       800 行 (15%)
```

### 技术栈
- **语言**: Python 3.10+
- **框架**: FastAPI, LlamaIndex, LangGraph
- **存储**: Qdrant, MySQL, MinIO
- **部署**: Docker, Docker Compose
- **依赖**: Poetry

---

**最后更新**: 2024-02-28
**版本**: v3.0
**状态**: ✅ 重构完成
