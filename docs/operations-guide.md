# RPKI 网络安全管理平台运维手册

本手册介绍 RPKI 网络安全管理平台的日常运维操作，涵盖服务管理、监控告警、备份恢复、日志管理、性能调优、安全运维与故障处理。

## 1. 服务管理

### 1.1 Docker Compose 环境

#### 启停服务

```bash
cd deploy

# 启动全部服务
docker-compose -f docker-compose.prod.yml up -d

# 停止全部服务
docker-compose -f docker-compose.prod.yml down

# 重启单个服务
docker-compose -f docker-compose.prod.yml restart backend

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps
```

#### 日志查看

```bash
# 查看后端日志（实时）
docker-compose -f docker-compose.prod.yml logs -f backend

# 查看最近 100 行日志
docker-compose -f docker-compose.prod.yml logs --tail=100 backend

# 查看指定时间段的日志
docker-compose -f docker-compose.prod.yml logs --since="2024-01-01T00:00:00" backend
```

#### 进入容器

```bash
# 进入后端容器
docker-compose -f docker-compose.prod.yml exec backend bash

# 进入数据库容器
docker-compose -f docker-compose.prod.yml exec postgres psql -U rpki rpki_platform
```

### 1.2 Kubernetes 环境

#### 启停服务

```bash
# 查看 Pod 状态
kubectl get pods -n rpki-platform

# 查看 Deployment
kubectl get deployments -n rpki-platform

# 重启后端（滚动重启）
kubectl rollout restart deployment rpki-backend -n rpki-platform

# 扩缩容
kubectl scale deployment rpki-backend --replicas=4 -n rpki-platform
```

#### 日志查看

```bash
# 查看 Pod 日志
kubectl logs -f deployment/rpki-backend -n rpki-platform

# 查看前一个容器的日志（崩溃后）
kubectl logs deployment/rpki-backend -n rpki-platform --previous
```

#### 进入 Pod

```bash
kubectl exec -it deployment/rpki-backend -n rpki-platform -- bash
```

## 2. 数据库运维

### 2.1 PostgreSQL 管理

#### 连接数据库

```bash
# Docker Compose
docker-compose -f docker-compose.prod.yml exec postgres psql -U rpki rpki_platform

# Kubernetes
kubectl exec -it statefulset/postgres -n rpki-platform -- psql -U rpki rpki_platform
```

#### 常用查询

```sql
-- 查看数据库大小
SELECT pg_size_pretty(pg_database_size('rpki_platform'));

-- 查看各表大小
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;

-- 查看活跃连接
SELECT count(*) FROM pg_stat_activity WHERE datname = 'rpki_platform';

-- 查看 VRP 数量
SELECT count(*) FROM vrps;

-- 查看 BGP 公告统计
SELECT
    rpki_validation_status,
    count(*)
FROM bgp_announcements
GROUP BY rpki_validation_status;

-- 查看告警统计
SELECT
    severity,
    status,
    count(*)
FROM alerts
GROUP BY severity, status
ORDER BY severity, status;
```

#### 数据库迁移

```bash
# 查看当前迁移版本
alembic current

# 查看迁移历史
alembic history

# 执行迁移
alembic upgrade head

# 回滚上一个迁移
alembic downgrade -1

# 创建新迁移
alembic revision --autogenerate -m "描述信息"
```

#### 索引维护

```sql
-- 查看索引使用情况
SELECT
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- 重建索引（在线）
REINDEX INDEX CONCURRENTLY ix_vrps_prefix;

-- 分析表（更新统计信息）
ANALYZE vrps;
ANALYZE bgp_announcements;
```

### 2.2 ClickHouse 管理

#### 连接 ClickHouse

```bash
# Docker Compose
docker-compose -f docker-compose.prod.yml exec clickhouse clickhouse-client

# HTTP 接口
curl 'http://localhost:8123/?query=SELECT+1'
```

#### 常用查询

```sql
-- 查看数据库大小
SELECT
    database,
    formatReadableSize(sum(bytes_on_disk)) AS size
FROM system.parts
WHERE active
GROUP BY database;

-- 查看 BGP 事件表大小
SELECT
    formatReadableSize(sum(bytes_on_disk)) AS size,
    count() AS rows
FROM rpki_platform.bgp_events
WHERE toDate(timestamp) >= today() - 7;

-- 查看分区情况
SELECT
    partition,
    formatReadableSize(sum(bytes_on_disk)) AS size,
    count() AS rows
FROM system.parts
WHERE database = 'rpki_platform' AND table = 'bgp_events' AND active
GROUP BY partition
ORDER BY partition;
```

#### 数据清理

```sql
-- 删除 30 天前的分区
ALTER TABLE rpki_platform.bgp_events
DROP PARTITION WHERE toYYYYMMDD(timestamp) < toYYYYMMDD(today() - 30);

-- 优化表（合并数据片段）
OPTIMIZE TABLE rpki_platform.bgp_events FINAL;
```

### 2.3 Redis 管理

```bash
# 连接 Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli -a <password>

# 查看内存使用
INFO memory

# 查看键空间
INFO keyspace

# 查看慢查询
SLOWLOG GET 10

# 清空缓存（谨慎）
FLUSHDB
```

## 3. 备份与恢复

### 3.1 备份策略

| 组件 | 备份频率 | 保留时长 | 备份方式 |
|------|----------|----------|----------|
| PostgreSQL | 每日 02:00 | 30 天 | pg_dump 全量 + WAL 归档 |
| ClickHouse | 每日 03:00 | 14 天 | 分区快照 |
| Redis | 每日 04:00 | 7 天 | RDB 快照 |
| Kafka | 按需 | 7 天 | 主题复制 |

### 3.2 PostgreSQL 备份

```bash
# 使用备份脚本
./scripts/backup/backup_postgres.sh

# 手动备份
docker-compose -f docker-compose.prod.yml exec postgres \
    pg_dump -U rpki -Fc rpki_platform > backup_$(date +%Y%m%d_%H%M%S).dump

# 备份压缩
docker-compose -f docker-compose.prod.yml exec postgres \
    pg_dump -U rpki rpki_platform | gzip > backup_$(date +%Y%m%d).sql.gz
```

### 3.3 PostgreSQL 恢复

```bash
# 使用恢复脚本
./scripts/backup/restore_postgres.sh backup_20240101.dump

# 手动恢复
docker-compose -f docker-compose.prod.yml exec -T postgres \
    pg_restore -U rpki -d rpki_platform -c < backup_20240101.dump
```

### 3.4 ClickHouse 备份

```bash
# 使用备份脚本
./scripts/backup/backup_clickhouse.sh

# 手动备份指定分区
clickhouse-client --query="
    ALTER TABLE rpki_platform.bgp_events
    FREEZE PARTITION '202401'
"
```

### 3.5 Redis 备份

```bash
# 使用备份脚本
./scripts/backup/backup_redis.sh

# 手动触发 RDB 快照
docker-compose -f docker-compose.prod.yml exec redis redis-cli -a <password> BGSAVE
```

### 3.6 完整备份

```bash
# 备份全部组件
./scripts/backup/backup_all.sh

# 恢复全部组件
./scripts/backup/restore_all.sh
```

### 3.7 定时备份（Cron）

```bash
# 编辑 crontab
crontab -e

# 添加定时备份任务
0 2 * * * /opt/rpki/scripts/backup/backup_postgres.sh >> /var/log/rpki_backup.log 2>&1
0 3 * * * /opt/rpki/scripts/backup/backup_clickhouse.sh >> /var/log/rpki_backup.log 2>&1
0 4 * * * /opt/rpki/scripts/backup/backup_redis.sh >> /var/log/rpki_backup.log 2>&1
```

## 4. 监控与告警

### 4.1 健康检查

```bash
# 后端健康检查
curl http://localhost:8000/health

# 预期返回
{
    "status": "healthy",
    "version": "1.0.0",
    "components": {
        "database": "healthy",
        "redis": "healthy",
        "kafka": "healthy",
        "clickhouse": "healthy"
    }
}
```

### 4.2 关键指标

#### 应用指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| 请求延迟 P99 | API 响应时间 | > 500ms |
| 错误率 | 5xx 错误占比 | > 1% |
| 活跃连接数 | 数据库连接池 | > 80% |
| 队列积压 | Kafka 消费延迟 | > 10000 条 |

#### 基础设施指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| CPU 使用率 | 各节点 CPU | > 80% |
| 内存使用率 | 各节点内存 | > 85% |
| 磁盘使用率 | 数据卷磁盘 | > 80% |
| 磁盘 IOPS | 数据卷 IOPS | > 阈值 |

#### 业务指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| VRP 数量 | 当前 VRP 总数 | 突变 > 20% |
| Invalid 路由数 | RPKI Invalid 公告 | 突增 |
| 告警待处理 | 新告警数量 | > 50 |
| RTR 客户端 | 连接的客户端数 | 突降 |

### 4.3 日志收集

建议使用 ELK（Elasticsearch + Logstash + Kibana）或 Loki + Grafana 收集日志：

```yaml
# docker-compose.prod.yml 增加 logging 配置
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"
        labels: "service,level"
```

### 4.4 告警配置

建议集成 Prometheus + AlertManager + Grafana：

- API 延迟突增
- 错误率上升
- 数据库连接数过高
- 磁盘空间不足
- 服务不可用

## 5. RPKI 特定运维

### 5.1 TAL 管理

```bash
# 查看 TAL 状态
curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rpki/tals

# 手动触发 TAL 同步
curl -X POST -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rpki/tals/1/sync
```

### 5.2 VRP 缓存更新

```bash
# 查看 VRP 缓存状态
curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rpki/cache

# 手动触发 VRP 同步
curl -X POST -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rpki/cache/sync
```

### 5.3 RTR 服务管理

```bash
# 查看 RTR 服务列表
curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rtr/servers

# 启动 RTR 服务
curl -X POST -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rtr/servers/1/start

# 停止 RTR 服务
curl -X POST -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rtr/servers/1/stop

# 检查 RTR 一致性
curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rtr/servers/1/consistency
```

### 5.4 ROA 管理

```bash
# 查看 ROA 列表
curl -H "Authorization: Bearer <token>" \
    "http://localhost:8000/api/v1/roas?page=1&page_size=20"

# 创建 ROA（需审批）
curl -X POST -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{
        "prefix": "10.0.0.0/8",
        "origin_as": 65001,
        "max_length": 16
    }' \
    http://localhost:8000/api/v1/roas
```

### 5.5 检测规则管理

```bash
# 查看检测规则
curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/detection/rules

# 启用/禁用规则
curl -X PATCH -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"enabled": false}' \
    http://localhost:8000/api/v1/detection/rules/1
```

## 6. 用户与权限管理

### 6.1 用户管理

```bash
# 创建用户
curl -X POST -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{
        "email": "user@example.com",
        "username": "newuser",
        "full_name": "新用户",
        "password": "StrongPassword123!",
        "tenant_id": 1
    }' \
    http://localhost:8000/api/v1/users

# 为用户分配角色
curl -X POST -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"role_id": 3}' \
    http://localhost:8000/api/v1/users/2/roles
```

### 6.2 角色与权限

系统内置角色：

| 角色 | 编码 | 权限范围 |
|------|------|----------|
| 超级管理员 | super_admin | 全部权限 |
| 网络管理员 | network_admin | 前缀/ROA/BGP 管理 |
| RPKI 管理员 | rpki_admin | RPKI 资源管理 |
| NOC 操作员 | noc_operator | 只读 + BGP 写入 |
| 安全分析师 | security_analyst | 审计与只读 |
| 审批人 | approver | ROA 审批 |
| 客户 | customer | 仅查看自身资源 |

### 6.3 密码策略

- 最小长度：12 字符
- 必须包含：大小写字母、数字、特殊字符
- 最大连续登录失败次数：5 次
- 账户锁定时长：15 分钟
- JWT 密钥轮换间隔：90 天

### 6.4 JWT 密钥轮换

```bash
# 1. 生成新密钥
NEW_KEY=$(openssl rand -hex 32)

# 2. 将当前密钥加入 PREVIOUS_SECRET_KEYS
# 编辑 .env.production：
# PREVIOUS_SECRET_KEYS=<旧密钥>
# SECRET_KEY=<新密钥>

# 3. 重启后端服务
docker-compose -f docker-compose.prod.yml restart backend
```

## 7. 性能调优

### 7.1 后端性能

#### Uvicorn Worker 数量

```bash
# 根据 CPU 核心数调整 worker
# 推荐：worker 数 = CPU 核心数 * 2 + 1
uvicorn app.main:app --workers 9
```

#### 数据库连接池

在 `.env.production` 中配置：

```bash
# 连接池大小（默认 10）
DB_POOL_SIZE=20
# 最大溢出（默认 20）
DB_MAX_OVERFLOW=40
# 连接超时（秒）
DB_POOL_TIMEOUT=30
```

### 7.2 数据库性能

#### PostgreSQL 调优

```sql
-- 修改配置（postgresql.conf）
shared_buffers = 2GB              -- 推荐内存的 25%
effective_cache_size = 6GB        -- 推荐内存的 75%
work_mem = 64MB
maintenance_work_mem = 512MB
max_connections = 200
```

#### 索引优化

```sql
-- VRP 查询索引（前缀匹配）
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_vrps_prefix_gin
ON vrps USING gin (prefix gin_trgm_ops);

-- BGP 公告时间索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bgp_announcements_timestamp_brin
ON bgp_announcements USING brin (timestamp);
```

### 7.3 ClickHouse 性能

```sql
-- 调整分区策略（按月分区）
ALTER TABLE rpki_platform.bgp_events
MODIFY PARTITION BY toYYYYMM(timestamp);

-- 设置 TTL（自动过期）
ALTER TABLE rpki_platform.bgp_events
MODIFY TTL timestamp + INTERVAL 90 DAY;
```

### 7.4 前端性能

- 启用 Gzip 压缩
- 配置静态资源缓存（Cache-Control）
- 使用 CDN 加速静态资源
- 启用 HTTP/2

## 8. 安全运维

### 8.1 安全审计

```bash
# 查看审计日志
curl -H "Authorization: Bearer <token>" \
    "http://localhost:8000/api/v1/audit/logs?page=1&page_size=50"

# 按用户筛选审计日志
curl -H "Authorization: Bearer <token>" \
    "http://localhost:8000/api/v1/audit/logs?user_id=2"
```

### 8.2 IP 白名单

在 `.env.production` 中配置：

```bash
IP_WHITELIST_ENABLED=true
IP_WHITELIST=10.0.0.0/8,192.168.0.0/16
IP_WHITELIST_PATHS=/api/v1/admin,/api/v1/users
```

### 8.3 速率限制

系统默认启用速率限制，配置参数：

```bash
# 登录接口速率限制
RATE_LIMIT_LOGIN=5/minute
# API 速率限制
RATE_LIMIT_API=100/minute
```

### 8.4 证书管理

```bash
# 查看证书有效期
openssl x509 -in cert.pem -noout -dates

# 续期证书（Let's Encrypt 示例）
certbot renew
```

### 8.5 安全扫描

```bash
# 运行安全扫描脚本
cd backend
./scripts/security/run_sast.sh
./scripts/security/scan_dependencies.sh
```

## 9. 故障处理

### 9.1 服务故障

#### 后端无法启动

1. 检查日志：`docker-compose logs backend`
2. 检查数据库连接：`DATABASE_URL` 配置
3. 检查迁移状态：`alembic current`
4. 检查依赖服务：PostgreSQL、Redis、Kafka、ClickHouse

#### 数据库连接耗尽

```sql
-- 查看活跃连接
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity
WHERE datname = 'rpki_platform';

-- 终止空闲连接
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'rpki_platform'
  AND state = 'idle'
  AND state_change < now() - interval '30 minutes';
```

#### Kafka 消费积压

```bash
# 查看消费者组延迟
kafka-consumer-groups --bootstrap-server localhost:9092 \
    --describe --group rpki-platform

# 重置消费位点（谨慎）
kafka-consumer-groups --bootstrap-server localhost:9092 \
    --group rpki-platform --topic bgp-events \
    --reset-offsets --to-latest --execute
```

### 9.2 数据问题

#### VRP 数据不一致

```bash
# 触发 VRP 一致性检查
curl -X POST -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rpki/cache/check

# 重新同步 VRP
curl -X POST -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rpki/cache/sync
```

#### RTR 序列号回滚

```bash
# 查看序列号历史
curl -H "Authorization: Bearer <token>" \
    http://localhost:8000/api/v1/rtr/servers/1/history

# 回滚到指定序列号
curl -X POST -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"target_serial": 100}' \
    http://localhost:8000/api/v1/rtr/servers/1/rollback
```

### 9.3 应急响应

#### BGP 劫持告警处理

1. 确认告警真实性（检查 BGP 公告、RPKI 验证状态）
2. 评估影响范围（受影响前缀、传播范围）
3. 启动应急预案：
   - 通知相关 AS 管理员
   - 联系上游提供商过滤异常路由
   - 发布 ROA 修正（如需要）
   - 记录处置过程

#### RPKI 失效处理

1. 检查 TAL 同步状态
2. 检查 RPKI 仓库连通性
3. 重新同步 VRP 缓存
4. 验证 RTR 服务推送
5. 通知下游路由器刷新

## 10. 日常运维检查清单

### 10.1 每日检查

- [ ] 查看服务健康状态
- [ ] 检查告警待处理数量
- [ ] 查看错误日志（ERROR 级别）
- [ ] 确认备份任务执行成功
- [ ] 检查磁盘空间使用率

### 10.2 每周检查

- [ ] 检查 VRP 数量变化趋势
- [ ] 检查 RTR 服务连接客户端数
- [ ] 审查用户权限变更
- [ ] 检查证书有效期
- [ ] 执行安全扫描

### 10.3 每月检查

- [ ] 审计日志归档
- [ ] 数据库性能分析
- [ ] ClickHouse 数据清理
- [ ] 密钥轮换检查
- [ ] 容量规划评估

## 11. 相关文档

- [部署指南](deployment-guide.md)
- [生产环境配置模板](../deploy/env.production.example)
- [备份恢复脚本](../scripts/backup/)
- [安全扫描脚本](../backend/scripts/security/)
