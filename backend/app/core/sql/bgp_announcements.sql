-- BGP 公告历史表
-- 存储 BGP 路由公告的历史记录，用于趋势分析与回溯

CREATE TABLE IF NOT EXISTS bgp_announcements (
    id              UUID            DEFAULT generateUUIDv4(),
    prefix          String          COMMENT '公告的网络前缀',
    origin_as       UInt32          COMMENT '起源 AS 号',
    as_path         Array(UInt32)   COMMENT 'AS 路径列表',
    next_hop        String          COMMENT '下一跳地址',
    communities     Array(String)   COMMENT 'BGP Community 列表',
    observation_point String        COMMENT '观测点（采集器标识）',
    timestamp       DateTime64(3, 'UTC') COMMENT '公告观测时间'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, prefix, origin_as)
SETTINGS index_granularity = 8192;
