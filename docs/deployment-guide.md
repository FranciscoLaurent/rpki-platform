# RPKI 网络安全管理平台部署指南

本指南介绍 RPKI 网络安全管理平台在生产环境中的部署流程，涵盖基础设施准备、容器化部署、Kubernetes 部署、数据库迁移、初始数据加载与部署验证。

## 1. 环境要求

### 1.1 硬件要求

| 组件 | 最小配置 | 推荐配置 | 说明 |
|------|----------|----------|------|
| 后端服务 | 2C 4G | 4C 8G | FastAPI + Uvicorn，4 worker |
| 前端服务 | 1C 1G | 2C 2G | Nginx 静态托管 |
| PostgreSQL | 2C 4G + 50G SSD | 4C 8G + 200G SSD | 主数据库，存储热数据 |
| Redis | 1C 1G | 2C 2G | 缓存与会话 |
| Kafka | 2C 4G + 50G | 4C 8G + 100G | 事件消息队列 |
| ClickHouse | 4C 8G + 200G SSD | 8C 16G + 500G SSD | BGP 历史数据时序存储 |

### 1.2 软件依赖

- Docker 24.0+ 与 docker-compose 2.20+
- Python 3.11+（仅源码部署需要）
- Node.js 18+（仅前端构建需要）
- Kubernetes 1.27+（K8s 部署需要）
- kubectl 与 helm（K8s 部署需要）

### 1.3 网络要求

- 后端服务端口：8000（内部）
- 前端服务端口：80/443（对外）
- PostgreSQL：5432（内部）
- Redis：6379（内部）
- Kafka：9092（内部）
- ClickHouse：8123/9000（内部）
- RTR 服务端口：8282/8283（对路由器开放）

## 2. 部署架构

```
                    ┌─────────────┐
                    │  负载均衡器  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
        ┌─────┴─────┐           ┌───────┴───────┐
        │  前端 Nginx │           │  后端 FastAPI  │
        │  (80/443)  │           │  (8000)       │
        └────────────┘           └───────┬───────┘
                                         │
              ┌──────────────┬───────────┼───────────┐
              │              │           │           │
        ┌─────┴─────┐ ┌──────┴─────┐ ┌───┴────┐ ┌────┴─────┐
        │ PostgreSQL │ │   Redis    │ │ Kafka  │ │ClickHouse│
        │  (5432)    │ │  (6379)    │ │(9092)  │ │ (8123)   │
        └────────────┘ └────────────┘ └────────┘ └──────────┘
```

## 3. Docker Compose 部署

### 3.1 准备配置

1. 复制生产环境配置模板：

```bash
cp deploy/env.production.example deploy/.env.production
```

2. 编辑 `.env.production`，**必须修改**以下项：

```bash
# 数据库密码（使用强随机密码）
POSTGRES_PASSWORD=<强随机密码>

# Redis 密码
REDIS_PASSWORD=<强随机密码>

# ClickHouse 密码
CLICKHOUSE_PASSWORD=<强随机密码>

# JWT 密钥（使用 64 字节随机字符串）
SECRET_KEY=$(openssl rand -hex 32)

# CORS 来源（填写实际域名）
CORS_ORIGINS=https://rpki.example.com
```

### 3.2 启动服务

```bash
# 切换到 deploy 目录
cd deploy

# 使用生产环境配置启动全部服务
docker-compose --env-file .env.production -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f backend
```

### 3.3 执行数据库迁移

```bash
# 在后端容器中执行迁移
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head

# 查看当前迁移版本
docker-compose -f docker-compose.prod.yml exec backend alembic current
```

### 3.4 初始化系统数据

系统首次启动时会自动初始化超级管理员账号与系统角色。如需手动初始化：

```bash
docker-compose -f docker-compose.prod.yml exec backend python -c \
    "import asyncio; from app.core.init_data import init_system_data; asyncio.run(init_system_data())"
```

### 3.5 加载示例数据（可选）

如需加载示例数据用于演示或验收：

```bash
# 写入全部示例数据
docker-compose -f docker-compose.prod.yml exec backend python -m scripts.init_sample_data

# 仅查看将写入的数据（不实际写入）
docker-compose -f docker-compose.prod.yml exec backend python -m scripts.init_sample_data --dry-run

# 仅写入租户与用户
docker-compose -f docker-compose.prod.yml exec backend python -m scripts.init_sample_data --only tenants users
```

## 4. Kubernetes 部署

### 4.1 准备命名空间

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl config set-context --current --namespace=rpki-platform
```

### 4.2 创建密钥与配置

```bash
# 编辑 secrets.yaml 中的密码与密钥
vi deploy/k8s/secrets.yaml

# 创建密钥
kubectl apply -f deploy/k8s/secrets.yaml

# 创建配置
kubectl apply -f deploy/k8s/configmap.yaml
```

### 4.3 部署基础设施

```bash
# PostgreSQL
kubectl apply -f deploy/k8s/postgres-statefulset.yaml

# Redis
kubectl apply -f deploy/k8s/redis-statefulset.yaml

# Kafka
kubectl apply -f deploy/k8s/kafka-statefulset.yaml

# ClickHouse
kubectl apply -f deploy/k8s/clickhouse-statefulset.yaml
```

### 4.4 部署应用

```bash
# 后端
kubectl apply -f deploy/k8s/backend-deployment.yaml

# 前端
kubectl apply -f deploy/k8s/frontend-deployment.yaml

# Ingress
kubectl apply -f deploy/k8s/ingress.yaml

# HPA（水平自动扩缩容）
kubectl apply -f deploy/k8s/hpa.yaml
```

### 4.5 执行迁移与初始化

```bash
# 执行数据库迁移
kubectl exec -it deploy/rpki-backend -- alembic upgrade head

# 初始化系统数据
kubectl exec -it deploy/rpki-backend -- python -c \
    "import asyncio; from app.core.init_data import init_system_data; asyncio.run(init_system_data())"
```

## 5. 源码部署（开发/测试）

### 5.1 启动基础设施

```bash
# 启动 PostgreSQL、Redis、Kafka、ClickHouse
make up
```

### 5.2 后端部署

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 修改数据库密码等配置

# 执行数据库迁移
alembic upgrade head

# 初始化系统数据
python -c "import asyncio; from app.core.init_data import init_system_data; asyncio.run(init_system_data())"

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5.3 前端部署

```bash
cd frontend

# 安装依赖
npm install

# 构建生产版本
npm run build

# 使用 Nginx 托管 dist/ 目录
# 配置参考 frontend/nginx.conf
```

## 6. TLS/SSL 配置

### 6.1 后端 TLS

在生产环境建议启用 TLS。配置 `.env.production`：

```bash
TLS_ENABLED=true
TLS_CERT_FILE=/path/to/cert.pem
TLS_KEY_FILE=/path/to/key.pem
TLS_MIN_VERSION=TLSv1.2
```

### 6.2 前端 Nginx TLS

修改 `frontend/nginx.conf`，配置 443 端口与证书：

```nginx
server {
    listen 443 ssl http2;
    server_name rpki.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.3 RTR 服务 mTLS

RTR 服务支持 mTLS 双向认证，在 RTR 服务配置中启用：

```python
RTRServer(
    name="生产 RTR 服务",
    listen_port=8282,
    mtls_enabled=True,
    config={
        "mtls_ca_file": "/path/to/ca.pem",
        "mtls_cert_file": "/path/to/server.crt",
        "mtls_key_file": "/path/to/server.key",
    },
)
```

## 7. 部署验证

### 7.1 健康检查

```bash
# 后端健康检查
curl http://localhost:8000/health

# 预期返回
# {"status": "healthy", "version": "1.0.0", ...}
```

### 7.2 服务连通性

```bash
# 数据库
docker-compose -f docker-compose.prod.yml exec postgres pg_isready -U rpki

# Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# Kafka
docker-compose -f docker-compose.prod.yml exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# ClickHouse
curl http://localhost:8123/ping
```

### 7.3 API 验证

```bash
# 登录获取令牌
curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "admin123"}'

# 使用令牌访问受保护接口
curl http://localhost:8000/api/v1/users/me \
    -H "Authorization: Bearer <token>"
```

### 7.4 前端验证

浏览器访问 `https://rpki.example.com`，使用默认管理员账号登录：

- 用户名：`admin`
- 密码：`admin123`

**首次登录后请立即修改密码。**

## 8. 升级部署

### 8.1 滚动升级（K8s）

```bash
# 更新镜像
kubectl set image deployment/rpki-backend backend=rpki/backend:v1.1.0

# 查看滚动升级状态
kubectl rollout status deployment/rpki-backend

# 如需回滚
kubectl rollout undo deployment/rpki-backend
```

### 8.2 Docker Compose 升级

```bash
cd deploy

# 拉取新镜像
docker-compose -f docker-compose.prod.yml pull

# 滚动更新
docker-compose -f docker-compose.prod.yml up -d --no-deps --build backend

# 执行数据库迁移
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 8.3 金丝雀发布

参考 `deploy/k8s/canary-deployment.yaml` 配置金丝雀发布：

```bash
kubectl apply -f deploy/k8s/canary-deployment.yaml
```

## 9. 备份与恢复

### 9.1 数据库备份

```bash
# 使用备份脚本
./scripts/backup/backup_postgres.sh

# 手动备份
docker-compose -f docker-compose.prod.yml exec postgres \
    pg_dump -U rpki rpki_platform > backup_$(date +%Y%m%d).sql
```

### 9.2 完整备份

```bash
# 备份全部组件
./scripts/backup/backup_all.sh

# 恢复全部组件
./scripts/backup/restore_all.sh
```

详细备份恢复操作请参考 `docs/operations-guide.md`。

## 10. 故障排查

### 10.1 服务无法启动

1. 检查日志：`docker-compose logs <service>`
2. 检查配置：确认 `.env.production` 中所有必填项已设置
3. 检查端口占用：`netstat -tlnp | grep -E '8000|5432|6379'`
4. 检查磁盘空间：`df -h`

### 10.2 数据库连接失败

1. 确认 PostgreSQL 已启动：`docker-compose ps postgres`
2. 确认 `DATABASE_URL` 配置正确
3. 确认密码与权限：`docker-compose exec postgres psql -U rpki -d rpki_platform`

### 10.3 迁移失败

```bash
# 查看当前迁移版本
docker-compose exec backend alembic current

# 查看迁移历史
docker-compose exec backend alembic history

# 回滚上一个迁移
docker-compose exec backend alembic downgrade -1

# 重试升级
docker-compose exec backend alembic upgrade head
```

### 10.4 前端无法访问后端

1. 检查 `CORS_ORIGINS` 配置是否包含前端域名
2. 检查 Nginx 反向代理配置
3. 检查后端服务是否正常运行
4. 浏览器开发者工具查看网络请求

## 11. 安全清单

部署前请确认以下安全项：

- [ ] 所有默认密码已修改（数据库、Redis、ClickHouse、管理员账号）
- [ ] `SECRET_KEY` 已替换为随机强密钥
- [ ] `CORS_ORIGINS` 已限制为实际域名
- [ ] TLS 已启用，证书有效
- [ ] IP 白名单已配置（如需要）
- [ ] 防火墙规则仅开放必要端口
- [ ] 数据库端口不对外暴露（仅绑定 127.0.0.1）
- [ ] 定期备份已配置
- [ ] 日志收集与告警已配置
- [ ] 密钥轮换策略已制定

## 12. 相关文档

- [运维手册](operations-guide.md)
- [生产环境配置模板](../deploy/env.production.example)
- [Kubernetes 部署配置](../deploy/k8s/)
- [备份恢复脚本](../scripts/backup/)
- [部署脚本](../scripts/deploy/)
