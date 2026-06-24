# RPKI Platform Backend

RPKI 网络安全管理平台后端服务。

## 技术栈

- Python 3.11+
- FastAPI — Web 框架
- SQLAlchemy 2.0 (async) — ORM
- Pydantic v2 — 数据校验
- Alembic — 数据库迁移
- httpx — 异步 HTTP 客户端（采集 RIPEstat / RIR TAL 数据）
- structlog — 结构化日志

## 快速开始

```bash
# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate    # Linux/macOS

# 安装依赖（开发模式）
pip install -e ".[dev]"

# 复制环境变量模板
cp .env.example .env
# 编辑 .env，按提示填写数据库、Redis、JWT 等配置

# 初始化数据库表
python _create_tables.py

# 启动开发服务器（默认 8001 端口）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

## 目录结构

```
backend/
├── app/                # 应用主代码
│   ├── api/            # API 路由
│   ├── core/           # 配置、安全、日志
│   ├── db/             # 数据库连接
│   ├── models/         # SQLAlchemy 模型
│   ├── schemas/        # Pydantic 模型
│   ├── services/       # 业务服务（含 RIPEstat / RIR 采集器）
│   └── main.py         # FastAPI 入口
├── alembic/            # 数据库迁移
├── tests/              # 测试
├── pyproject.toml      # 项目配置
└── .env.example        # 环境变量模板
```

## 代码质量

```bash
ruff check .            # 代码检查
black --check .         # 格式检查
mypy app                # 类型检查
pytest -v               # 运行测试
```

## 安全说明

- `SECRET_KEY`、`DEFAULT_ADMIN_PASSWORD` 等敏感配置必须通过环境变量设置
- 生产环境务必覆盖 `pyproject.toml` / `config.py` 中的默认值
- 详细配置项见 `.env.example`
