# Kubernetes 部署清单

RPKI 网络安全管理平台 Kubernetes 生产级部署配置，支持高可用、弹性伸缩、灰度发布与灾备恢复。

## 目录结构

```
k8s/
├── README.md                          # 本文档
├── namespace.yaml                     # 命名空间定义
├── configmap.yaml                     # 非敏感配置映射
├── secrets.yaml                       # 敏感配置（占位，生产环境使用外部密钥管理）
├── postgres-statefulset.yaml          # PostgreSQL StatefulSet（3 副本高可用）
├── redis-statefulset.yaml             # Redis StatefulSet（3 副本 + Sentinel）
├── kafka-statefulset.yaml             # Kafka StatefulSet（3 副本 KRaft 模式）
├── clickhouse-statefulset.yaml        # ClickHouse StatefulSet（2 副本）
├── backend-deployment.yaml            # 后端 Deployment（3 副本）
├── frontend-deployment.yaml           # 前端 Deployment（2 副本）
├── ingress.yaml                       # Ingress 入口路由（含灰度配置）
├── hpa.yaml                           # HPA 自动扩缩容 + PDB 中断预算
├── canary-deployment.yaml             # 灰度发布 Deployment
└── multi-region/
    └── README.md                      # 多区域部署指南（同城双活 + 异地灾备）
```

## 部署架构

```
                        ┌──────────────────┐
                        │  Ingress (TLS)   │
                        │  rpki.example.com│
                        └────────┬─────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
       │  Frontend   │   │  Backend    │   │  Backend    │
       │  (2 副本)   │   │  (3 副本)   │   │  Canary     │
       │  nginx      │   │  FastAPI    │   │  (灰度)     │
       └─────────────┘   └──────┬──────┘   └─────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
   ┌──────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
   │ PostgreSQL  │      │   Redis     │      │   Kafka     │
   │  3 副本     │      │  3 副本+    │      │  3 副本     │
   │  流复制     │      │  Sentinel   │      │  KRaft 模式 │
   └─────────────┘      └─────────────┘      └─────────────┘
                                │
                        ┌──────▼──────┐
                        │ ClickHouse  │
                        │  2 副本     │
                        │  Replicated │
                        └─────────────┘
```

## 资源规格

| 组件 | 副本数 | CPU (req/limit) | 内存 (req/limit) | 存储 |
|------|--------|-----------------|------------------|------|
| PostgreSQL | 3 | 500m / 2000m | 1Gi / 4Gi | 50Gi |
| Redis | 3 | 100m / 500m | 256Mi / 1Gi | 10Gi |
| Kafka | 3 | 500m / 2000m | 1Gi / 4Gi | 50Gi |
| ClickHouse | 2 | 500m / 2000m | 1Gi / 4Gi | 100Gi |
| Backend | 3-10 (HPA) | 250m / 1000m | 512Mi / 2Gi | - |
| Frontend | 2-6 (HPA) | 100m / 500m | 128Mi / 512Mi | - |

## 快速开始

### 前置条件

- Kubernetes 1.26+
- kubectl 已配置集群访问
- Ingress Controller（nginx-ingress 推荐）
- StorageClass（建议 SSD）
- Metrics Server（HPA 依赖）
- 镜像仓库可访问（`rpki-platform/backend:latest`、`rpki-platform/frontend:latest`）

### 1. 创建命名空间与配置

```bash
# 创建命名空间
kubectl apply -f namespace.yaml

# 创建配置映射
kubectl apply -f configmap.yaml

# 创建密钥（生产环境请先修改占位值）
# 生成 base64 编码：echo -n 'your-password' | base64
kubectl apply -f secrets.yaml
```

### 2. 部署有状态服务

```bash
# PostgreSQL（3 副本，流复制高可用）
kubectl apply -f postgres-statefulset.yaml

# Redis（3 副本 + Sentinel 自动故障转移）
kubectl apply -f redis-statefulset.yaml

# Kafka（3 副本，KRaft 模式无 Zookeeper）
kubectl apply -f kafka-statefulset.yaml

# ClickHouse（2 副本，ReplicatedMergeTree）
kubectl apply -f clickhouse-statefulset.yaml

# 等待所有有状态服务就绪
kubectl -n rpki-platform wait --for=condition=ready pod -l app.kubernetes.io/name=postgres --timeout=300s
kubectl -n rpki-platform wait --for=condition=ready pod -l app.kubernetes.io/name=redis --timeout=300s
kubectl -n rpki-platform wait --for=condition=ready pod -l app.kubernetes.io/name=kafka --timeout=300s
kubectl -n rpki-platform wait --for=condition=ready pod -l app.kubernetes.io/name=clickhouse --timeout=300s
```

### 3. 部署应用服务

```bash
# 后端 Deployment（3 副本）
kubectl apply -f backend-deployment.yaml

# 前端 Deployment（2 副本）
kubectl apply -f frontend-deployment.yaml

# HPA 自动扩缩容 + PDB 中断预算
kubectl apply -f hpa.yaml

# Ingress 入口路由
kubectl apply -f ingress.yaml
```

### 4. 验证部署

```bash
# 查看所有资源
kubectl -n rpki-platform get all

# 检查 Pod 状态
kubectl -n rpki-platform get pods -o wide

# 检查服务端点
kubectl -n rpki-platform get endpoints

# 测试后端健康检查
kubectl -n rpki-platform port-forward svc/backend 8000:8000
curl http://localhost:8000/api/v1/health

# 测试前端
kubectl -n rpki-platform port-forward svc/frontend 8080:80
curl http://localhost:8080
```

## 高可用机制

### 数据库高可用

- **PostgreSQL**：3 副本流复制，主节点故障自动切换（需配合 Patroni/Operator）
- **Redis**：3 副本 + Sentinel，主节点故障 Sentinel 自动选举新主
- **Kafka**：3 副本 KRaft 模式，`replication.factor=3`，`min.insync.replicas=2`
- **ClickHouse**：2 副本 ReplicatedMergeTree，配合 ZooKeeper/Keeper 协调

### 应用高可用

- **多副本**：Backend 3 副本，Frontend 2 副本，跨节点反亲和调度
- **HPA 自动扩缩**：CPU > 70% 自动扩容，最低 3 副本，最高 10 副本
- **PDB 中断预算**：保证节点维护时最少可用副本数
- **健康探针**：readiness/liveness/startup 三级探针，异常自动重启
- **优雅关闭**：preStop 钩子等待请求处理完成

### 故障自动切换

| 故障场景 | 切换机制 | RTO |
|---------|---------|-----|
| Backend Pod 故障 | Deployment 自动重建 | < 30s |
| Frontend Pod 故障 | Deployment 自动重建 | < 30s |
| PostgreSQL 主故障 | Patroni/Sentinel 自动切换 | < 60s |
| Redis 主故障 | Sentinel 自动选举 | < 30s |
| Kafka Broker 故障 | KRaft 控制器重新选举 | < 30s |
| 节点故障 | Pod 重新调度 | < 120s |

## 灰度发布

### 灰度发布流程

```bash
# 1. 部署灰度版本（5% 流量）
./scripts/deploy/canary_deploy.sh backend rpki-platform/backend:v2.0.0

# 2. 观察灰度版本指标
kubectl -n rpki-platform logs -l app.kubernetes.io/variant=canary -f

# 3. 逐步增加流量（5% -> 20% -> 50% -> 100%）
# 脚本自动执行各阶段，每阶段观察后确认

# 4. 异常时自动回退
# 脚本检测到异常会自动将流量切回稳定版
```

### 滚动更新

```bash
# 普通滚动更新
./scripts/deploy/rolling_update.sh backend rpki-platform/backend:v1.2.0

# 查看更新状态
kubectl -n rpki-platform rollout status deployment/backend

# 查看修订历史
kubectl -n rpki-platform rollout history deployment/backend
```

### 版本回退

```bash
# 回退到上一版本
./scripts/deploy/rollback.sh backend

# 回退到指定版本
./scripts/deploy/rollback.sh backend 3
```

## 备份与恢复

### 备份策略

- **PostgreSQL**：每日全量 + 每小时增量（WAL 归档），保留 7 天
- **Redis**：每日 RDB 快照 + AOF 文件，保留 7 天
- **ClickHouse**：每日全量备份，保留 7 天

### 执行备份

```bash
# 统一备份（顺序执行所有服务备份）
./scripts/backup/backup_all.sh

# 并行备份
BACKUP_MODE=parallel ./scripts/backup/backup_all.sh

# 单独备份
./scripts/backup/backup_postgres.sh --full
./scripts/backup/backup_postgres.sh --incremental
./scripts/backup/backup_redis.sh
./scripts/backup/backup_clickhouse.sh
```

### 执行恢复

```bash
# 统一恢复（按时间戳）
./scripts/backup/restore_all.sh 20240101_120000

# 单独恢复
./scripts/backup/restore_postgres.sh /data/backups/postgres/full/postgres_full_20240101_120000.sql.gz
./scripts/backup/restore_redis.sh /data/backups/redis/full/redis_20240101_120000.tar.gz
./scripts/backup/restore_clickhouse.sh /data/backups/clickhouse/full/clickhouse_20240101_120000.tar.gz
```

### 定时备份（CronJob）

建议通过 K8s CronJob 定时执行备份：

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: rpki-platform
spec:
  schedule: "0 2 * * *"  # 每日凌晨 2 点
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:15-alpine
              command: ["/scripts/backup_postgres.sh", "--full"]
              # ... 挂载脚本与备份卷
          restartPolicy: OnFailure
```

## 配置说明

### 环境变量

应用配置通过 ConfigMap 与 Secret 注入，支持环境变量覆盖：

| 配置项 | 来源 | 默认值 | 说明 |
|--------|------|--------|------|
| APP_NAME | ConfigMap | RPKI 网络安全管理平台 | 应用名称 |
| DEBUG | ConfigMap | false | 调试模式 |
| DATABASE_URL | Secret | - | 数据库连接串 |
| REDIS_URL | Secret | - | Redis 连接串 |
| KAFKA_BOOTSTRAP_SERVERS | ConfigMap | kafka-0...:9092 | Kafka 引导服务器 |
| SECRET_KEY | Secret | - | JWT 签名密钥 |
| ACCESS_TOKEN_EXPIRE_MINUTES | ConfigMap | 120 | Token 过期时间 |

### 密钥管理

生产环境推荐使用外部密钥管理方案：

- **Sealed Secrets**：加密密钥可纳入 Git 仓库
- **External Secrets Operator**：对接 Vault / AWS Secrets Manager / 阿里云 KMS
- **HashiCorp Vault**：集中式密钥管理，动态密钥生成

## 监控与可观测性

### 推荐监控栈

- **Prometheus**：指标采集
- **Grafana**：指标可视化
- **Loki**：日志聚合
- **Jaeger**：链路追踪
- **AlertManager**：告警管理

### 关键监控指标

- Pod CPU / 内存使用率
- 数据库连接数 / 慢查询
- Redis 命中率 / 内存使用
- Kafka 消费者滞后 / 副本同步
- HTTP 请求 QPS / 错误率 / 延迟
- HPA 扩缩容事件

## 多区域部署

详见 [multi-region/README.md](multi-region/README.md)，包含：

- 同城双活架构（跨 AZ 高可用）
- 异地灾备方案（跨区域数据同步）
- 故障切换流程
- RTO / RPO 目标

## 升级与维护

### 集群升级

1. 先升级有状态服务（PostgreSQL、Redis、Kafka、ClickHouse）
2. 再升级无状态服务（Backend、Frontend）
3. 使用滚动更新，逐个替换 Pod
4. 监控升级过程，异常及时回退

### 数据库迁移

```bash
# 执行 Alembic 数据库迁移
kubectl -n rpki-platform exec deploy/backend -- \
  alembic upgrade head

# 查看当前版本
kubectl -n rpki-platform exec deploy/backend -- \
  alembic current
```

### 节点维护

```bash
# 标记节点为不可调度
kubectl cordon <node-name>

# 驱逐节点上的 Pod
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# 维护完成后恢复
kubectl uncordon <node-name>
```

## 故障排查

### 常见问题

```bash
# Pod 处于 Pending 状态（资源不足或调度失败）
kubectl -n rpki-platform describe pod <pod-name>

# Pod 处于 CrashLoopBackOff（应用启动失败）
kubectl -n rpki-platform logs <pod-name> --previous

# Service 无端点（标签不匹配或 Pod 未就绪）
kubectl -n rpki-platform get endpoints <service-name>

# PVC 绑定失败（StorageClass 不存在或容量不足）
kubectl -n rpki-platform get pvc
```

### 日志查看

```bash
# 查看应用日志
kubectl -n rpki-platform logs -l app.kubernetes.io/name=backend --tail=100

# 实时跟踪日志
kubectl -n rpki-platform logs -l app.kubernetes.io/name=backend -f

# 查看指定 Pod 日志
kubectl -n rpki-platform logs <pod-name>
```

## 生产环境建议

1. **镜像管理**：使用具体版本标签，避免 `latest`；建立镜像漏洞扫描
2. **资源限制**：所有容器设置 requests/limits，避免资源争抢
3. **网络策略**：配置 NetworkPolicy 限制 Pod 间通信
4. **安全上下文**：runAsNonRoot=true，readOnlyRootFilesystem=true（如可能）
5. **Pod 安全标准**：启用 restricted 级别 Pod Security Standards
6. **备份验证**：定期执行恢复演练，验证备份有效性
7. **监控告警**：关键指标告警，故障自动通知
8. **容量规划**：定期评估资源使用，提前扩容
