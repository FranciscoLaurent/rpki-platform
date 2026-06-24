# 后端 Dockerfile：多阶段构建
# 阶段一：构建依赖
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /build

# 安装构建依赖（asyncpg 等需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖声明文件
COPY pyproject.toml ./

# 安装依赖到独立目录，便于后续复制
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --target=/install \
        "fastapi>=0.110.0" \
        "uvicorn[standard]>=0.27.0" \
        "sqlalchemy[asyncio]>=2.0.25" \
        "asyncpg>=0.29.0" \
        "alembic>=1.13.0" \
        "pydantic>=2.6.0" \
        "pydantic-settings>=2.1.0" \
        "python-jose[cryptography]>=3.3.0" \
        "passlib[bcrypt]>=1.7.4" \
        "python-multipart>=0.0.9" \
        "redis>=5.0.0" \
        "kafka-python>=2.0.2" \
        "clickhouse-connect>=0.7.0" \
        "httpx>=0.26.0" \
        "structlog>=24.1.0"

# 阶段二：运行时
FROM python:3.11-slim AS runtime

# 安装运行时依赖（libpq 用于 asyncpg）
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 从构建阶段复制已安装的依赖
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# 复制应用代码
COPY . .

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
