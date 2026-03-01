# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 1. 项目概览

Enterprise-grade **Multimodal Agentic RAG** (Retrieval-Augmented Generation) system with full-dimension ablation experiment support.

**核心特性**：
- **微服务架构**: 3 services (Indexing, Agent, Testing) + 2 storage backends (Qdrant, MySQL)
- **多模态处理**: PDF image-text pair extraction, VLM summarization, hierarchical storage (MySQL + Qdrant)
- **Agent 推理**: LangGraph ReAct workflow, parallel question routing, SSE streaming
- **消融实验**: Grid-based ablation testing across chunking, retrieval, and reranking dimensions
- **角色过滤**: Chinese filename-based role extraction (teacher/student/reviewer/admin)
- **轻量稀疏向量**: jieba-based sparse vectors (~15MB) replacing BGE-M3 (~2GB)

**技术栈**: LlamaIndex, LangGraph, Qdrant, MySQL, FastAPI, DashScope (Qwen-Plus, Qwen-VL)

---

## 2. 快速开始

### 一键启动（推荐）

```bash
docker compose up -d
# Indexing API:     http://localhost:8001/docs
# Agent API:        http://localhost:8002/docs
# Qdrant UI:        http://localhost:6333/dashboard
```

### 本地开发（各服务独立 Poetry 环境）

```bash
# 启动存储层
docker run -d -p 6333:6333 qdrant/qdrant
docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=rag_password -e MYSQL_DATABASE=rag_db mysql:8.0
mysql -h localhost -u root -prag_password < scripts/init_mysql.sql

# 启动各服务
cd services/indexing && poetry install && poetry run python -m app.main
cd services/agent && poetry install && poetry run python -m app.main
```

### 运行测试

```bash
docker compose exec testing pytest app/tests/ -v
```

---

## 3. 关键文件索引

| 功能 | 文件位置 |
|------|----------|
| **ComponentRegistry** | `services/indexing/app/core/registry.py` |
| **Abstract Base Classes** | `services/indexing/app/core/types.py` |
| **ExperimentConfig** | `services/indexing/app/config/experiment.py` |
| **Role Mapper** | `services/indexing/app/utils/role_mapper.py` |
| **Indexing API** | `services/indexing/app/api/routes.py` |
| **Agent API** | `services/agent/app/api/routes.py` |
| **IngestionService** | `services/indexing/app/services/ingestion.py` |
| **RetrievalService** | `services/indexing/app/services/retrieval.py` |
| **MultimodalRetrievalService** | `services/indexing/app/services/multimodal_retrieval.py` |
| **PDFToMarkdownService** | `services/indexing/app/services/pdf_to_markdown.py` |
| **LangGraph Workflow** | `services/agent/app/agent/workflow.py` |
| **LangGraph Nodes** | `services/agent/app/agent/nodes.py` |
| **LangGraph Tools** | `services/agent/app/agent/tools.py` |
| **PolicyCleaner** | `services/indexing/app/parsing/cleaner.py` |
| **Multimodal Parser** | `services/indexing/app/parsing/multimodal_parser.py` |
| **Jieba Sparse Vectors** | `services/indexing/app/components/providers/bgem3.py` |
| **VLM Provider (Ingestion)** | `services/indexing/app/components/providers/vlm.py` |
| **VLM Service (Agent)** | `services/agent/app/services/vlm.py` |
| **Multimodal Chunker** | `services/indexing/app/components/chunkers/multimodal.py` |
| **VectorStoreManager** | `services/indexing/app/storage/vectordb.py` |
| **MySQLClient** | `services/indexing/app/storage/mysql_client.py` |
| **MySQL Init Script** | `scripts/init_mysql.sql` |

---

## 4. 详细文档

- 架构设计 → `.claude/rules/references/architecture.md`
- 服务 API → `.claude/rules/references/services.md`
- 核心实现与配置 → `.claude/rules/references/implementation.md`
- 多模态架构 → `.claude/rules/references/multimodal.md`
- 运维与故障排查 → `.claude/rules/references/operations.md`
