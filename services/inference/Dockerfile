FROM python:3.11-slim-bookworm

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Poetry
RUN pip install --no-cache-dir poetry

# 先复制 shared 库
COPY shared/ /shared/

# 复制服务依赖定义
COPY services/inference/pyproject.toml services/inference/poetry.lock* ./

# 安装依赖
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# 复制服务代码
COPY services/inference/app/ ./app/

# 安装项目本身
RUN poetry install --no-interaction --no-ansi

EXPOSE 8002

CMD ["uvicorn", "app.main:app_instance", "--host", "0.0.0.0", "--port", "8002"]
