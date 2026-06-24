.PHONY: help dev build test lint format migrate up down logs clean install-backend install-frontend

# 默认目标
help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# 安装依赖
install-backend: ## 安装后端依赖
	cd backend && pip install -e ".[dev]"

install-frontend: ## 安装前端依赖
	cd frontend && npm install

install: install-backend install-frontend ## 安装全部依赖

# 开发服务
dev-backend: ## 启动后端开发服务
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## 启动前端开发服务
	cd frontend && npm run dev

dev: ## 启动前后端开发服务（需分别运行 dev-backend / dev-frontend）
	@echo "请分别在两个终端运行: make dev-backend 和 make dev-frontend"

# 构建
build-backend: ## 构建后端
	cd backend && pip install -e .

build-frontend: ## 构建前端
	cd frontend && npm run build

build: build-backend build-frontend ## 构建前后端

# 测试
test-backend: ## 运行后端测试
	cd backend && pytest -v

test-frontend: ## 运行前端测试
	cd frontend && npm run test --if-present

test: test-backend test-frontend ## 运行全部测试

# 代码检查
lint-backend: ## 后端代码检查
	cd backend && ruff check . && black --check . && mypy app

lint-frontend: ## 前端代码检查
	cd frontend && npm run lint

lint: lint-backend lint-frontend ## 全部代码检查

format-backend: ## 后端代码格式化
	cd backend && ruff check --fix . && black .

format-frontend: ## 前端代码格式化
	cd frontend && npm run format

format: format-backend format-frontend ## 全部代码格式化

# 数据库迁移
migrate: ## 执行数据库迁移
	cd backend && alembic upgrade head

migrate-create: ## 创建新迁移（用法: make migrate-create m="消息"）
	cd backend && alembic revision --autogenerate -m "$(m)"

migrate-rollback: ## 回滚上一个迁移
	cd backend && alembic downgrade -1

# Docker 基础设施
up: ## 启动基础设施容器
	cd deploy && docker-compose up -d

down: ## 停止基础设施容器
	cd deploy && docker-compose down

logs: ## 查看基础设施日志
	cd deploy && docker-compose logs -f

# 清理
clean: ## 清理构建产物与缓存
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf backend/dist backend/build backend/*.egg-info
	rm -rf frontend/dist frontend/node_modules/.vite
