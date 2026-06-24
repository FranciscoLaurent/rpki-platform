-- BGP 事件表
-- 存储 BGP 异常事件，如路由泄露、前缀劫持、起源 AS 伪造等

CREATE TABLE IF NOT EXISTS bgp_events (
    id              UUID            DEFAULT generateUUIDv4(),
    event_type      String          COMMENT '事件类型：route_leak, prefix_hijack, origin_spoof 等',
    prefix          String          COMMENT '涉及的网络前缀，如 192.168.1.0/24',
    origin_as       UInt32          COMMENT '起源 AS 号',
    as_path         Array(UInt32)   COMMENT 'AS 路径列表',
    observation_point String        COMMENT '观测点（采集器标识）',
    timestamp       DateTime64(3, 'UTC') COMMENT '事件发生时间',
    raw_data        String          COMMENT '原始 BGP 消息（JSON）',
    created_at      DateTime64(3, 'UTC') DEFAULT now() COMMENT '记录创建时间'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, event_type, prefix)
SETTINGS index_granularity = 8192;
