# 🚀 快速参考卡片 - v3.0 微服务架构

## 服务端口

| 服务 | 端口 | 用途 |
|------|------|------|
| **Orchestrator** | 8000 | 用户入口、流程编排 |
| **Indexing** | 8001 | 解析、切片、向量化、检索 |
| **Agent** | 8002 | LLM/VLM 推理、ReAct 工作流 |
| **Testing** | 8003 | 集中测试管理 |
| Qdrant | 6333 | 向量数据库 |
| MySQL | 3306 | 关系数据库 |
| MinIO | 9000, 9001 | 对象存储 |

---

## 快速启动

```bash
# 1. 启动基础设施
docker compose up -d qdrant mysql minio minio-init

# 2. 验证基础设施
bash scripts/verify_infrastructure.sh

# 3. 启动所有服务
docker compose up -d

# 4. 验证服务
curl http://localhost:8000/health  # Orchestrator
curl http://localhost:8001/health  # Indexing
curl http://localhost:8002/health  # Agent
curl http://localhost:8003/health  # Testing
```

---

## API 端点速查

### Orchestrator (8000)
- `POST /api/v1/upload` - 文件上传
- `POST /api/v1/chat` - 对话（SSE）
- `POST /api/v1/ingest-and-chat` - 端到端流程
- `GET /api/v1/collections` - 列出 collections
- `GET /health` - 健康检查

### Indexing (8001)
- `POST /api/v1/ingest` - 文档入库
- `POST /api/v1/retrieve` - 检索
- `POST /api/v1/rerank` - 重排序
- `GET /api/v1/collections` - 列出 collections
- `GET /api/v1/collections/{name}/files` - 列出文件
- `DELETE /api/v1/collections/{name}` - 删除 collection
- `DELETE /api/v1/documents/{collection}/{filename}` - 删除文档
- `GET /health` - 健康检查

### Agent (8002)
- `POST /api/v1/chat` - 对话（SSE）
- `POST /api/v1/chat/reset` - 重置对话
- `POST /api/v1/vlm/analyze` - VLM 图像分析
- `POST /api/v1/vlm/summarize` - VLM 批量摘要
- `GET /health` - 健康检查

### Testing (8003)
- `POST /api/v1/tests/run` - 运行测试
- `GET /api/v1/tests/results` - 测试结果列表
- `GET /api/v1/tests/results/{id}` - 测试结果详情
- `DELETE /api/v1/tests/results/{id}` - 删除结果
- `GET /health` - 健康检查

---

## 测试命令

```bash
# 上传文档
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test.pdf" \
  -F 'config={"collection_name":"test"}'

# 对话
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"测试","config":{"collection_name":"test"},"thread_id":"test123"}'

# 运行测试
curl -X POST http://localhost:8003/api/v1/tests/run \
  -H "Content-Type: application/json" \
  -d '{"suite":"e2e-pipeline"}'
```

---

## 环境变量

```bash
# 必需
DASHSCOPE_API_KEY=sk-your-key-here

# 服务 URL（Docker 内部）
INDEXING_URL=http://indexing:8001
AGENT_URL=http://agent:8002
ORCHESTRATOR_URL=http://orchestrator:8000

# 存储（Docker 内部）
QDRANT_URL=http://qdrant:6333
MYSQL_URL=mysql+pymysql://rag_user:rag_password@mysql:3306/rag_db
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

---

## 目录结构

```
my_rag_project/
├── services/
│   ├── orchestrator/    # Port 8000
│   ├── indexing/        # Port 8001
│   ├── agent/           # Port 8002
│   └── testing/         # Port 8003
├── scripts/
│   ├── init_mysql.sql
│   ├── verify_infrastructure.sh
│   └── verify_refactoring.sh
├── docker-compose.yml
├── .env.example
└── docs/
```

---

## 文档索引

| 文档 | 用途 |
|------|------|
| `REFACTORING_COMPLETE.md` | 重构完成总结 |
| `EXECUTION_SUMMARY.md` | 执行总结 |
| `PROJECT_STRUCTURE.md` | 项目结构总览 |
| `GIT_COMMIT_GUIDE.md` | Git 提交指南 |
| `FINAL_CHECKLIST.md` | 最终检查清单 |
| `QUICK_REFERENCE.md` | 本文档 |

---

## 故障排查

### 服务无法启动
```bash
# 查看日志
docker compose logs -f <service>

# 重启服务
docker compose restart <service>

# 重建服务
docker compose build <service>
docker compose up -d <service>
```

### 健康检查失败
```bash
# 检查容器状态
docker compose ps

# 检查网络
docker network inspect my_rag_project_rag_network

# 检查环境变量
docker compose exec <service> env
```

### 数据库连接失败
```bash
# 检查 MySQL
docker compose exec mysql mysql -u rag_user -prag_password -e "SHOW DATABASES;"

# 检查 Qdrant
curl http://localhost:6333/health

# 检查 MinIO
curl http://localhost:9000/minio/health/live
```

---

## Git 提交

```bash
# 单次提交
git add .
git commit -m "refactor: 微服务架构重构 v2.0 → v3.0"
git push origin main

# 创建标签
git tag -a v3.0.0 -m "微服务架构重构完成"
git push origin v3.0.0
```

---

## 重构成果

- ✅ 4 个职责纯粹的微服务
- ✅ 0 个共享库依赖
- ✅ 3 个外部存储
- ✅ 40% 代码精简
- ✅ 完整文档体系

**版本**: v3.0
**状态**: ✅ 准备投入生产
**日期**: 2024-02-28
