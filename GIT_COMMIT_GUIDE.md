# Git 提交指南 - 微服务架构重构 v3.0

## 提交概览

### 变更统计
- **变更文件数**: 145 个
- **新增服务**: 4 个（Indexing, Agent, Orchestrator, Testing）
- **删除服务**: 5 个（shared, ingestion, inference, gateway, cli）
- **代码精简**: 40% (~3461 行)

---

## 提交策略

### 选项 1: 单次提交（推荐）
适合快速记录完整重构。

```bash
git add .
git commit -m "refactor: 微服务架构重构 v2.0 → v3.0

完成 Phase 1-6 全部重构任务：

Phase 1: 基础设施
- 添加 MinIO 对象存储
- 扩展 MySQL schema（4张表）
- 更新 docker-compose.yml

Phase 2: Indexing Service (Port 8001)
- 合并 ingestion + retrieval + shared
- 8 个 API 端点
- 5 种切片策略 + 混合检索

Phase 3: Agent Service (Port 8002)
- LangGraph ReAct 工作流
- VLM 分析服务
- SSE 流式输出

Phase 4: Orchestrator Service (Port 8000)
- 用户入口、流程编排
- 文件上传到 MinIO
- 端到端流程

Phase 5: Testing Service (Port 8003)
- 集中测试管理
- 4 个测试套件
- 结果持久化

Phase 6: 清理旧代码
- 删除 shared/, services/ingestion/, services/inference/, services/gateway/, cli/
- 代码精简 40%

架构改进：
- 服务职责清晰化（单一职责）
- 消除共享库依赖（HTTP API 通信）
- 存储外部化（MinIO/Qdrant/MySQL）
- 测试集中管理

Breaking Changes:
- 删除 shared 库
- 删除旧服务（ingestion, inference, gateway）
- 删除 CLI 工具
- 端口变更：Orchestrator 8000（新）, Indexing 8001, Agent 8002, Testing 8003（新）

文档：
- REFACTORING_STATUS.md
- REFACTORING_COMPLETE.md
- PHASE6_CLEANUP_REPORT.md
- PROJECT_STRUCTURE.md
- 各服务 README.md

Refs: docs/refactoring-plan.md"
```

### 选项 2: 分阶段提交
适合详细记录每个阶段。

```bash
# Phase 1: 基础设施
git add docker-compose.yml scripts/init_mysql.sql .env.example scripts/verify_infrastructure.sh
git commit -m "feat: Phase 1 - 基础设施搭建

- 添加 MinIO 对象存储（raw-documents, extracted-images buckets）
- 扩展 MySQL schema（parent_nodes, collections, documents, test_runs）
- 更新 docker-compose.yml（健康检查）
- 添加基础设施验证脚本"

# Phase 2: Indexing Service
git add services/indexing/
git commit -m "feat: Phase 2 - Indexing Service 实现

- 合并 ingestion + retrieval + shared 功能
- 8 个 API 端点（ingest, retrieve, rerank, collections, files, delete）
- 5 种切片策略（fixed, recursive, sentence, semantic, multimodal）
- 混合检索（Dense + Sparse + Reranking）
- MinIO 文件存储
- 角色过滤（Chinese filename-based）
- 迁移 shared 库（types, registry, config, utils）"

# Phase 3: Agent Service
git add services/agent/
git commit -m "feat: Phase 3 - Agent Service 实现

- LangGraph ReAct 工作流（5 节点）
- VLM 分析服务（DashScope Qwen-VL）
- SSE 流式输出（token, rewrite, chunks, done, error）
- HTTP 调用 Indexing Service（无直接 DB 访问）
- 5 个 API 端点（chat, vlm/analyze, vlm/summarize）"

# Phase 4: Orchestrator Service
git add services/orchestrator/
git commit -m "feat: Phase 4 - Orchestrator Service 实现

- 用户入口、流程编排
- 文件上传到 MinIO
- 5 个 API 端点（upload, chat, ingest-and-chat, collections）
- 3 个服务客户端（Indexing, Agent, MinIO）
- SSE 流式代理
- 端到端流程（上传 + 入库 + 对话）"

# Phase 5: Testing Service
git add services/testing/
git commit -m "feat: Phase 5 - Testing Service 实现

- 集中测试管理
- 4 个测试套件（indexing, agent, orchestrator, e2e）
- pytest + JSON 报告
- 结果持久化（MySQL test_runs 表）
- 5 个 API 端点（run, results, delete）"

# Phase 6: 清理旧代码
git add -A
git commit -m "refactor: Phase 6 - 清理旧代码

删除：
- shared/ (已迁移到 Indexing Service)
- services/ingestion/ (已合并到 Indexing Service)
- services/inference/ (已拆分到 Agent Service)
- services/gateway/ (已替换为 Orchestrator Service)
- cli/ (已替换为 Testing Service)

代码精简：
- 删除 ~8500 行
- 新增 ~5039 行
- 精简 40% (3461 行)

文档：
- REFACTORING_STATUS.md
- REFACTORING_COMPLETE.md
- PHASE6_CLEANUP_REPORT.md
- PROJECT_STRUCTURE.md"

# 更新文档
git add CLAUDE.md README.md docs/
git commit -m "docs: 更新架构文档

- 更新 CLAUDE.md（v3.0 架构）
- 更新 README.md（快速开始）
- 添加重构文档（REFACTORING_*, PROJECT_STRUCTURE.md）"
```

---

## 提交前检查清单

### 代码检查
- [ ] 所有新服务目录完整
- [ ] 旧服务目录已删除
- [ ] docker-compose.yml 配置正确
- [ ] .env.example 更新完整
- [ ] 所有 pyproject.toml 配置正确

### 文档检查
- [ ] REFACTORING_STATUS.md 完整
- [ ] REFACTORING_COMPLETE.md 完整
- [ ] PHASE6_CLEANUP_REPORT.md 完整
- [ ] PROJECT_STRUCTURE.md 完整
- [ ] 各服务 README.md 完整

### 功能检查
- [ ] 基础设施配置正确（Qdrant, MySQL, MinIO）
- [ ] 所有服务 Dockerfile 正确
- [ ] 所有服务 Poetry 配置正确
- [ ] 服务间依赖关系正确

---

## 推送到远程

### 推送到主分支
```bash
git push origin main
```

### 创建标签
```bash
git tag -a v3.0.0 -m "微服务架构重构完成

- 4 个职责纯粹的微服务
- 0 个共享库依赖
- 3 个外部存储
- 40% 代码精简
- 完整文档体系"

git push origin v3.0.0
```

### 创建发布分支
```bash
git checkout -b release/v3.0
git push -u origin release/v3.0
```

---

## 回滚方案

### 回滚到重构前
```bash
# 查看重构前的提交
git log --oneline | grep "before refactoring"

# 回滚（假设提交 hash 为 abc123）
git reset --hard abc123

# 或者创建回滚分支
git checkout -b rollback/v2.0 abc123
```

### 恢复单个文件
```bash
# 恢复 shared 库
git checkout HEAD~1 -- shared/

# 恢复旧服务
git checkout HEAD~1 -- services/ingestion/
git checkout HEAD~1 -- services/inference/
git checkout HEAD~1 -- services/gateway/
git checkout HEAD~1 -- cli/
```

---

## Git 统计

### 查看变更统计
```bash
# 文件变更统计
git diff --stat HEAD~1

# 代码行数变更
git diff --shortstat HEAD~1

# 详细变更
git diff --stat --summary HEAD~1
```

### 查看新增/删除文件
```bash
# 新增文件
git diff --name-status HEAD~1 | grep "^A"

# 删除文件
git diff --name-status HEAD~1 | grep "^D"

# 修改文件
git diff --name-status HEAD~1 | grep "^M"
```

---

## 提交后验证

### 1. 克隆验证
```bash
# 克隆到新目录
git clone <repo-url> test-clone
cd test-clone

# 验证文件结构
ls -la services/

# 验证服务完整性
cd services/indexing && ls -la app/
cd services/agent && ls -la app/
cd services/orchestrator && ls -la app/
cd services/testing && ls -la app/
```

### 2. 构建验证
```bash
# 构建所有服务
docker compose build

# 启动所有服务
docker compose up -d

# 验证服务健康
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### 3. 功能验证
```bash
# 运行测试套件
curl -X POST http://localhost:8003/api/v1/tests/run \
  -H "Content-Type: application/json" \
  -d '{"suite":"e2e-pipeline"}'
```

---

## 注意事项

### Breaking Changes
⚠️ 本次重构包含破坏性变更：
- 删除 shared 库（所有依赖 shared 的代码需更新）
- 删除旧服务（ingestion, inference, gateway）
- 删除 CLI 工具（替换为 Testing Service）
- 端口变更（Orchestrator 8000, Testing 8003）

### 迁移指南
如果有外部系统依赖旧服务：
1. **Ingestion API** → 使用 Indexing Service (Port 8001)
2. **Inference API** → 使用 Agent Service (Port 8002)
3. **Gateway UI** → 使用 Orchestrator Service (Port 8000)
4. **CLI 工具** → 使用 Testing Service API (Port 8003)

### 环境变量变更
新增环境变量：
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `INDEXING_URL`
- `AGENT_URL`
- `ORCHESTRATOR_URL`
- `TESTING_URL`

---

## 推荐提交命令

```bash
# 单次提交（推荐）
git add .
git commit -F- <<EOF
refactor: 微服务架构重构 v2.0 → v3.0

完成 Phase 1-6 全部重构任务，实现 4 个职责纯粹的微服务架构。

新增服务：
- Orchestrator Service (Port 8000) - 用户入口、流程编排
- Indexing Service (Port 8001) - 解析、切片、向量化、检索
- Agent Service (Port 8002) - LLM/VLM 推理、ReAct 工作流
- Testing Service (Port 8003) - 集中测试管理

删除服务：
- shared/ - 已迁移到 Indexing Service
- services/ingestion/ - 已合并到 Indexing Service
- services/inference/ - 已拆分到 Agent Service
- services/gateway/ - 已替换为 Orchestrator Service
- cli/ - 已替换为 Testing Service

架构改进：
- 服务职责清晰化（单一职责原则）
- 消除共享库依赖（HTTP API 通信）
- 存储外部化（MinIO/Qdrant/MySQL）
- 测试集中管理（Testing Service）
- 代码精简 40% (~3461 行)

Breaking Changes:
- 删除 shared 库
- 端口变更：Orchestrator 8000, Testing 8003
- API 端点变更（详见各服务 README.md）

文档：
- REFACTORING_STATUS.md - 重构状态跟踪
- REFACTORING_COMPLETE.md - 重构完成总结
- PHASE6_CLEANUP_REPORT.md - 清理报告
- PROJECT_STRUCTURE.md - 项目结构总览
- 各服务 README.md - 服务文档

Refs: docs/refactoring-plan.md
EOF

# 推送
git push origin main

# 创建标签
git tag -a v3.0.0 -m "微服务架构重构完成"
git push origin v3.0.0
```

---

**最后更新**: 2024-02-28
**版本**: v3.0
**状态**: ✅ 准备提交
