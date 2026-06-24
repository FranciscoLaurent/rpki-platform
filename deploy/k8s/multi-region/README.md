# 多区域部署指南

本文档描述 RPKI 网络安全管理平台的多区域高可用部署架构，涵盖同城双活与异地灾备两种方案。

## 一、架构总览

```
                        ┌─────────────────────────────┐
                        │      全局负载均衡 (GSLB)     │
                        │   DNS / Anycast / GeoDNS    │
                        └──────────┬──────────┬───────┘
                                   │          │
                  ┌────────────────┘          └────────────────┐
                  │                                            │
        ┌─────────▼─────────┐                       ┌──────────▼──────────┐
        │   区域 A (主)      │                       │   区域 B (备/活)    │
        │   Region Primary   │                       │   Region Standby    │
        ├─────────────────────┤                       ├─────────────────────┤
        │  AZ-1   AZ-2 (双活) │                       │  AZ-1   AZ-2 (双活) │
        │  ┌───┐  ┌───┐       │                       │  ┌───┐  ┌───┐       │
        │  │K8s│  │K8s│       │                       │  │K8s│  │K8s│       │
        │  └─┬─┘  └─┬─┘       │                       │  └─┬─┘  └─┬─┘       │
        │    │      │         │                       │    │      │         │
        │  ┌─▼──────▼─┐       │                       │  ┌─▼──────▼─┐       │
        │  │ PG主从   │       │                       │  │ PG主从   │       │
        │  │ Redis    │       │                       │  │ Redis    │       │
        │  │ Kafka    │       │                       │  │ Kafka    │       │
        │  │ClickHouse│       │                       │  │ClickHouse│       │
        │  └──────────┘       │                       │  └──────────┘       │
        └─────────┬───────────┘                       └──────────┬──────────┘
                  │                                              │
                  └────────────── 异地数据同步 ──────────────────┘
                        (PG 流复制 / Kafka MirrorMaker /
                         ClickHouse Replicated / Redis Replication)
```

## 二、同城双活方案

### 2.1 架构特点

- **同一城市，两个可用区（AZ）**：网络延迟 < 1ms，带宽充足
- **两个 AZ 同时承载流量**：任一 AZ 故障，另一 AZ 接管全部流量
- **数据强一致性**：主数据库跨 AZ 同步复制

### 2.2 部署拓扑

| 组件 | AZ-1 | AZ-2 | 说明 |
|------|------|------|------|
| K8s 控制面 | 3 节点（跨 AZ） | - | etcd 跨 AZ 多数派 |
| K8s 工作节点 | N 节点 | N 节点 | Pod 反亲和跨 AZ 调度 |
| PostgreSQL | Primary + Replica | Replica | 流复制，故障自动切换 |
| Redis | Master + Slave | Slave | Sentinel 跨 AZ 部署 |
| Kafka | Broker 1 | Broker 2,3 | replication.factor=3, min.insync=2 |
| ClickHouse | Replica 1 | Replica 2 | ReplicatedMergeTree + ZooKeeper |
| Backend | 副本组 1 | 副本组 2 | 通过 Service 负载均衡 |
| Frontend | 副本组 1 | 副本组 2 | 通过 Ingress 负载均衡 |

### 2.3 跨 AZ 调度配置

通过 `topologySpreadConstraints` 实现 Pod 跨 AZ 均匀分布：

```yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app.kubernetes.io/name: backend
```

通过 `podAntiAffinity` 避免单点：

```yaml
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchLabels:
              app.kubernetes.io/name: postgres
          topologyKey: topology.kubernetes.io/zone
```

### 2.4 数据同步

- **PostgreSQL**：同步流复制（synchronous_commit=on），保证 RPO=0
- **Redis**：Sentinel 跨 AZ 部署，故障自动切换
- **Kafka**：`min.insync.replicas=2`，`acks=all`，跨 AZ 副本
- **ClickHouse**：ReplicatedMergeTree + 跨 AZ ZooKeeper/Keeper 集群

## 三、异地灾备方案

### 3.1 架构特点

- **不同城市，两个区域**：网络延迟 10-50ms，适合异步复制
- **主区域承载全部流量，备区域待命**：主区域故障时切换
- **数据最终一致性**：异步复制，RPO > 0（通常 < 1 分钟）

### 3.2 部署拓扑

| 组件 | 区域 A（主） | 区域 B（备） | 同步方式 |
|------|-------------|-------------|----------|
| K8s 集群 | 独立集群 | 独立集群 | 各自独立 |
| PostgreSQL | Primary 集群 | Standby 集群 | 异步流复制 / 逻辑复制 |
| Redis | Master | Replica | 异步复制 |
| Kafka | 主集群 | MirrorMaker | Kafka MirrorMaker 2 |
| ClickHouse | 主集群 | 副本集群 | ReplicatedMergeTree 异步 |
| 对象存储 | 主桶 | 备桶 | 跨区域复制 |

### 3.3 数据同步方案

#### PostgreSQL 异地同步

**方案一：物理流复制（异步）**

```ini
# 区域 A postgresql.conf
wal_level = replica
max_wal_senders = 10
synchronous_commit = off  # 异步提交

# 区域 B recovery.conf
primary_conninfo = 'host=region-a-postgres port=5432 user=replicator'
restore_command = 'cp /var/lib/postgresql/wal_archive/%f %p'
```

**方案二：逻辑复制（推荐，支持选择性同步）**

```sql
-- 区域 A：创建发布
CREATE PUBLICATION rpki_pub FOR ALL TABLES;

-- 区域 B：创建订阅
CREATE SUBSCRIPTION rpki_sub
  CONNECTION 'host=region-a-postgres port=5432 user=replicator'
  PUBLICATION rpki_pub;
```

#### Kafka 异地同步（MirrorMaker 2）

```properties
# mm2.properties
clusters = primary, dr
primary.bootstrap.servers = region-a-kafka:9092
dr.bootstrap.servers = region-b-kafka:9092

primary->dr.enabled = true
primary->dr.topics = .*
replication.factor = 3
sync.group.offsets.enabled = true
```

#### ClickHouse 异地同步

使用 `ReplicatedMergeTree` 配合跨区域 ZooKeeper，或使用 `Distributed` 表引擎异步聚合。

### 3.4 故障切换流程

1. **检测故障**：监控主区域健康状态（探针、心跳）
2. **决策切换**：人工或自动决策（避免脑裂）
3. **提升备区域**：
   - PostgreSQL：`pg_promote()` 提升备库为主
   - Redis：Sentinel 自动故障转移
   - Kafka：切换 MirrorMaker 为生产者
4. **流量切换**：GSLB / DNS 将流量指向备区域
5. **验证服务**：健康检查、冒烟测试
6. **数据修复**：原主区域恢复后，反向同步数据

### 3.5 RTO 与 RPO 目标

| 场景 | RTO（恢复时间） | RPO（数据丢失） |
|------|----------------|----------------|
| 同城双活（AZ 故障） | < 1 分钟 | 0 |
| 异地灾备（区域故障） | < 30 分钟 | < 1 分钟 |
| 异地灾备（手动切换） | < 5 分钟 | < 1 分钟 |

## 四、备份与恢复

### 4.1 备份策略

- **本地备份**：每日全量 + 每小时增量，保留 7 天
- **异地备份**：每日全量同步到对象存储，保留 30 天
- **跨区域复制**：对象存储跨区域复制（CRR）

### 4.2 备份脚本

使用 `scripts/backup/` 下的统一备份脚本：

```bash
# 本地全量备份
./scripts/backup/backup_all.sh

# 异地备份同步（推送到对象存储）
aws s3 sync /data/backups s3://rpki-backup-dr/$(date +%Y%m%d)/ \
  --storage-class STANDARD_IA
```

### 4.3 恢复演练

- **每月**：执行一次异地灾备恢复演练
- **每季度**：执行一次完整的故障切换演练
- **记录**：演练报告、问题跟踪、改进措施

## 五、监控与告警

### 5.1 关键监控指标

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| PostgreSQL 复制延迟 | > 5s | 主从同步延迟 |
| Redis 主从延迟 | > 1s | 主从同步延迟 |
| Kafka 消费者滞后 | > 10000 | 消费者积压 |
| 跨区域同步延迟 | > 60s | 异地复制延迟 |
| Pod 重启次数 | > 3 次/小时 | 异常重启 |
| 节点 NotReady | > 0 | 节点不可用 |

### 5.2 健康检查探针

- **Liveness**：服务存活检查
- **Readiness**：服务就绪检查（含依赖检查）
- **Startup**：慢启动服务检查

## 六、网络与安全

### 6.1 网络连通性

- 同城双活：VPC 互通，内网直连
- 异地灾备：专线 / VPN / SD-WAN 互通
- 带宽规划：峰值带宽的 1.5 倍冗余

### 6.2 安全要求

- 跨区域传输加密：TLS 1.3
- 数据库连接加密：SSL/TLS
- 网络隔离：安全组 / NetworkPolicy
- 密钥管理：HashiCorp Vault 跨区域同步

## 七、实施清单

### 7.1 同城双活实施

- [ ] 多 AZ K8s 集群部署
- [ ] 跨 AZ 节点亲和性配置
- [ ] PostgreSQL 跨 AZ 流复制
- [ ] Redis Sentinel 跨 AZ 部署
- [ ] Kafka 跨 AZ 副本配置
- [ ] ClickHouse 跨 AZ 副本配置
- [ ] 跨 AZ 负载均衡配置
- [ ] 故障切换演练

### 7.2 异地灾备实施

- [ ] 备区域 K8s 集群部署
- [ ] PostgreSQL 逻辑复制配置
- [ ] Kafka MirrorMaker 2 部署
- [ ] ClickHouse 跨区域复制
- [ ] 对象存储跨区域复制
- [ ] GSLB / DNS 切换配置
- [ ] 监控告警跨区域联动
- [ ] 灾备恢复演练

## 八、参考文档

- [PostgreSQL High Availability](https://www.postgresql.org/docs/15/high-availability.html)
- [Redis Sentinel Documentation](https://redis.io/docs/management/sentinel/)
- [Kafka MirrorMaker 2](https://kafka.apache.org/documentation/#georeplication)
- [ClickHouse Replication](https://clickhouse.com/docs/en/guides/sre/keeper)
- [Kubernetes Multi-Region](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/ha-topology/)
