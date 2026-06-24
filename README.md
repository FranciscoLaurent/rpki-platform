# RPKI 网络安全管理平台

企业级 RPKI（资源公钥基础设施）网络安全管理平台，用于 BGP 路由安全监测、ROA 管理、告警事件处理与资产管控。

## 技术栈

- **后端**: Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2
- **前端**: React 18 + TypeScript + Vite + Ant Design 5 + React Query + React Router 6
- **数据库**: PostgreSQL 16
- **缓存**: Redis 7
- **消息队列**: Kafka (Confluent)
- **时序数据库**: ClickHouse（BGP 事件与历史数据）
- **容器化**: Docker + docker-compose
- **CI/CD**: GitHub Actions

## 目录结构

```
RPKI_software/
├── backend/      # 后端工程（FastAPI）
├── frontend/     # 前端工程（React + Vite）
├── deploy/       # 部署配置（docker-compose、k8s）
├── .github/      # CI/CD 工作流
├── Makefile      # 常用命令快捷方式
└── README.md
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker 与 docker-compose

### 启动基础设施

```bash
make up              # 启动 PostgreSQL、Redis、Kafka、ClickHouse
```

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问健康检查：http://localhost:8000/health

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问：http://localhost:5173

## 常用命令

```bash
make dev        # 启动前后端开发服务
make build      # 构建前后端
make test       # 运行测试
make lint       # 代码检查
make migrate    # 执行数据库迁移
make up         # 启动基础设施容器
make down       # 停止基础设施容器
```

## 许可证

私有项目，版权所有。
