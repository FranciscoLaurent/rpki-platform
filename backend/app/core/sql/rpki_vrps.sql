-- VRP 历史快照表
-- 存储 RPKI VRP（Validated ROA Payload）的历史快照，用于追踪 VRP 变更

CREATE TABLE IF NOT EXISTS rpki_vrps (
    id              UUID            DEFAULT generateUUIDv4(),
    prefix          String          COMMENT '网络前缀',
    origin_as       UInt32          COMMENT '授权的起源 AS 号',
    max_length      UInt8           COMMENT '最大前缀长度',
    tal             String          COMMENT '信任锚标签（Trust Anchor Locator）',
    snapshot_time   DateTime64(3, 'UTC') COMMENT '快照时间'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(snapshot_time)
ORDER BY (snapshot_time, prefix, origin_as)
SETTINGS index_granularity = 8192;
