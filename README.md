# 🤖 企业级 Agentic RAG 系统 (科研与实验增强版)

本项目是一个基于 **LlamaIndex**、**LangGraph** 和 **Qdrant** 构建的高性能检索增强生成（RAG）系统。系统采用“配置驱动”与“策略工厂”设计模式，专为科研消融实验（Ablation Study）和多租户数据隔离而优化。

---

## 🌟 核心特性

* **🧪 配置驱动开发 (CDD)**：通过外部 YAML 配置文件动态调整模型、路径及检索策略，支持“一键切换”实验方案。
* **🧱 多租户数据隔离**：利用 SQLite 联合唯一约束与 Qdrant 动态集合绑定，确保不同实验组间的数据物理隔离。
* **🏭 策略工厂模式**：内置 `ModelFactory` 生产线，支持 `fixed`、`recursive`、`sentence` 等切片算法动态插拔。
* **🔍 高级检索流水线**：集成混合检索（Hybrid Search）、自动合并（Auto-Merging）和 Rerank 重排序技术。
* **📊 零依赖评测工具**：内置评测脚本，支持 Hit Rate、MRR、NDCG 计算，并实现终端视觉像素级对齐输出。

---

## 🏗️ 系统架构

系统遵循“三权分立”设计原则，确保各组件松耦合：

1. **指挥官 (Orchestrator)**：`server.py` 协调 UI 交互与业务流转。
2. **账本层 (Ledger)**：`database.py` (SQLite) 记录文件元数据与所属实验分区。
3. **加工层 (Processing)**：`ingestion.py` 执行文件读取、切片与向量入库。
4. **存储层 (Memory)**：`store.py` (Qdrant) 维护物理向量数据。

---

## 🛠️ 技术栈

* **核心框架**：LlamaIndex 0.13.0+, LangGraph 0.2.0。
* **大模型/向量**：阿里云 DashScope (Qwen-Plus, text-embedding-v4)。
* **稀疏向量**：BGE-M3 (FlagEmbedding) 增强中文检索能力。
* **数据库**：Qdrant (向量)、SQLite (元数据)。
* **前端界面**：Gradio 5.0。

---

## 🚀 快速开始

### 1. 环境安装

使用 Poetry 进行依赖管理：

```bash
poetry install

```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
DASHSCOPE_API_KEY=您的阿里云API密匙

```

### 3. 运行项目

使用默认配置启动系统：

```bash
python src/app/main.py

```

如需加载特定实验配置：

```bash
python src/app/main.py --config configs/exp_recursive.yaml

```

---

## 🧪 消融实验与评测

使用内置脚本评估检索质量：

```bash
# 测试默认方案的前 10 条数据
python scripts/evaluate_retrieval.py --limit 10

```

---

## 📂 项目结构

```text
my_rag_project/
├── configs/            # 实验配置文件 (YAML)
├── scripts/            # 评测、诊断与探针工具
├── src/app/
│   ├── api/           # UI 界面与交互逻辑
│   ├── core/
│   │   ├── engine/    # 核心引擎 (加工、检索、存储、工厂)
│   │   └── graph/     # LangGraph 工作流定义
│   ├── settings.py    # 动态配置加载器
│   └── main.py        # 程序统一入口
└── pyproject.toml      # 依赖管理配置文件

```

---

## ⚠️ 重要说明

* **数据库重置**：因架构升级至多租户隔离，若检测到旧版结构，请删除 `metadata.db` 重新初始化。
* **网络环境**：系统内置国内镜像设置，支持 BGE-M3 模型从 ModelScope 自动下载。