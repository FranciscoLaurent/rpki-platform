// BGP 监测页面
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertOutlined,
  DatabaseOutlined,
  EyeOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import {
  getBGPAnnouncements,
  getBGPSources,
  getBGPStats,
  getBGPWithdraws,
  getObservationPoints,
} from '@/api/bgp';
import type {
  BGPAnnouncement,
  BGPSource,
  BGPWithdraw,
} from '@/api/bgp';

const { Text } = Typography;

/** 数据源状态颜色映射 */
const SOURCE_STATUS_COLOR: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  error: 'red',
};

/** RPKI 验证状态颜色映射 */
const RPKI_STATUS_COLOR: Record<string, string> = {
  valid: 'green',
  invalid: 'red',
  not_found: 'orange',
};

/** RPKI 验证状态标签映射 */
const RPKI_STATUS_LABEL: Record<string, string> = {
  valid: 'Valid',
  invalid: 'Invalid',
  not_found: 'NotFound',
};

/** 信任等级颜色映射 */
const TRUST_LEVEL_COLOR: Record<string, string> = {
  high: 'green',
  medium: 'blue',
  low: 'orange',
};

/** 每页显示条数 */
const PAGE_SIZE = 10;

/** BGP 监测页面 */
function BgpMonitor() {
  const [announcementPage, setAnnouncementPage] = useState(1);
  const [withdrawPage, setWithdrawPage] = useState(1);

  /** 拉取 BGP 统计数据，每 30 秒自动刷新 */
  const {
    data: stats,
    isLoading: statsLoading,
    isFetching: statsFetching,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ['bgp-stats'],
    queryFn: getBGPStats,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  /** 拉取 BGP 数据源列表 */
  const { data: sources, isLoading: sourcesLoading } = useQuery({
    queryKey: ['bgp-sources'],
    queryFn: () => getBGPSources({ limit: 100 }),
  });

  /** 拉取观察点列表（用于公告/撤路中观察点 ID → 名称映射） */
  const { data: observationPoints } = useQuery({
    queryKey: ['bgp-observation-points'],
    queryFn: () => getObservationPoints({ limit: 200 }),
  });

  /** 拉取最近 BGP 公告 */
  const { data: announcements, isLoading: announcementsLoading } = useQuery({
    queryKey: ['bgp-announcements'],
    queryFn: () => getBGPAnnouncements({ limit: 100 }),
  });

  /** 拉取最近 BGP 撤路 */
  const { data: withdraws, isLoading: withdrawsLoading } = useQuery({
    queryKey: ['bgp-withdraws'],
    queryFn: () => getBGPWithdraws({ limit: 100 }),
  });

  /** 观察点 ID → 名称 映射 */
  const observationPointMap = useMemo(() => {
    const map = new Map<number, string>();
    observationPoints?.forEach((p) => {
      map.set(p.id, p.name);
    });
    return map;
  }, [observationPoints]);

  /** 数据源表格列定义 */
  const sourceColumns: ColumnsType<BGPSource> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 120,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '协议',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 100,
    },
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={SOURCE_STATUS_COLOR[v] || 'default'}>{v}</Tag>
      ),
    },
    {
      title: '信任等级',
      dataIndex: 'trust_level',
      key: 'trust_level',
      width: 110,
      render: (v: string) => (
        <Tag color={TRUST_LEVEL_COLOR[v] || 'default'}>{v}</Tag>
      ),
    },
  ];

  /** 公告表格列定义 */
  const announcementColumns: ColumnsType<BGPAnnouncement> = [
    {
      title: '前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      width: 200,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '起源 AS',
      dataIndex: 'origin_as',
      key: 'origin_as',
      width: 110,
      render: (v: number | null) => (v != null ? `AS${v}` : '-'),
    },
    {
      title: 'AS_PATH',
      dataIndex: 'as_path',
      key: 'as_path',
      render: (v: number[] | null) =>
        v && v.length > 0 ? v.join(' → ') : '-',
    },
    {
      title: '观察点',
      dataIndex: 'observation_point_id',
      key: 'observation_point_id',
      width: 140,
      render: (v: number | null) =>
        v != null ? observationPointMap.get(v) ?? `#${v}` : '-',
    },
    {
      title: '验证状态',
      dataIndex: 'rpki_validation_status',
      key: 'rpki_validation_status',
      width: 120,
      render: (v: string | null) =>
        v ? (
          <Tag color={RPKI_STATUS_COLOR[v] || 'default'}>
            {RPKI_STATUS_LABEL[v] ?? v}
          </Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
    },
  ];

  /** 撤路表格列定义 */
  const withdrawColumns: ColumnsType<BGPWithdraw> = [
    {
      title: '前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '观察点',
      dataIndex: 'observation_point_id',
      key: 'observation_point_id',
      width: 200,
      render: (v: number | null) =>
        v != null ? observationPointMap.get(v) ?? `#${v}` : '-',
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
    },
  ];

  /** 公告分页配置 */
  const announcementPagination: TablePaginationConfig = {
    current: announcementPage,
    pageSize: PAGE_SIZE,
    total: announcements?.length ?? 0,
    showSizeChanger: false,
    showTotal: (total) => `共 ${total} 条`,
    onChange: (page) => setAnnouncementPage(page),
  };

  /** 撤路分页配置 */
  const withdrawPagination: TablePaginationConfig = {
    current: withdrawPage,
    pageSize: PAGE_SIZE,
    total: withdraws?.length ?? 0,
    showSizeChanger: false,
    showTotal: (total) => `共 ${total} 条`,
    onChange: (page) => setWithdrawPage(page),
  };

  /** 渲染加载中 */
  if (statsLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="加载 BGP 监测数据..." />
      </div>
    );
  }

  return (
    <PageContainer
      title="BGP 监测"
      subtitle="实时监测 BGP 数据源、公告与撤路记录"
      extra={
        <Button
          icon={<ReloadOutlined />}
          onClick={() => refetchStats()}
          loading={statsFetching}
        >
          刷新
        </Button>
      }
    >
      {/* 顶部统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable styles={{ body: { padding: 24 } }}>
            <Statistic
              title="数据源总数"
              value={stats?.total_data_sources ?? 0}
              prefix={<DatabaseOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                活跃 {stats?.active_data_sources ?? 0}
              </Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable styles={{ body: { padding: 24 } }}>
            <Statistic
              title="观察点总数"
              value={stats?.total_observation_points ?? 0}
              prefix={<EyeOutlined style={{ color: '#722ed1' }} />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable styles={{ body: { padding: 24 } }}>
            <Statistic
              title="公告总数"
              value={stats?.total_announcements ?? 0}
              prefix={<AlertOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
            <div style={{ marginTop: 8 }}>
              <Space size={4} wrap>
                <Tag color="green">
                  Valid {stats?.announcements_by_rpki_status?.valid ?? 0}
                </Tag>
                <Tag color="red">
                  Invalid {stats?.announcements_by_rpki_status?.invalid ?? 0}
                </Tag>
                <Tag color="orange">
                  NotFound {stats?.announcements_by_rpki_status?.not_found ?? 0}
                </Tag>
              </Space>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable styles={{ body: { padding: 24 } }}>
            <Statistic
              title="撤路记录数"
              value={stats?.total_withdraws ?? 0}
              prefix={<RollbackOutlined style={{ color: '#fa8c16' }} />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      {/* BGP 数据源表格 */}
      <Card
        title="BGP 数据源"
        styles={{ body: { padding: 0 } }}
        style={{ marginTop: 16 }}
      >
        <Table<BGPSource>
          rowKey="id"
          columns={sourceColumns}
          dataSource={sources}
          loading={sourcesLoading}
          pagination={false}
          size="small"
          scroll={{ x: 800 }}
          locale={{ emptyText: <Empty description="暂无数据源" /> }}
        />
      </Card>

      {/* 最近 BGP 公告 */}
      <Card
        title="最近 BGP 公告"
        styles={{ body: { padding: 0 } }}
        style={{ marginTop: 16 }}
      >
        <Table<BGPAnnouncement>
          rowKey="id"
          columns={announcementColumns}
          dataSource={announcements}
          loading={announcementsLoading}
          pagination={announcementPagination}
          size="small"
          scroll={{ x: 900 }}
          locale={{ emptyText: <Empty description="暂无公告记录" /> }}
        />
      </Card>

      {/* 撤路记录 */}
      <Card
        title="撤路记录"
        styles={{ body: { padding: 0 } }}
        style={{ marginTop: 16 }}
      >
        <Table<BGPWithdraw>
          rowKey="id"
          columns={withdrawColumns}
          dataSource={withdraws}
          loading={withdrawsLoading}
          pagination={withdrawPagination}
          size="small"
          locale={{ emptyText: <Empty description="暂无撤路记录" /> }}
        />
      </Card>
    </PageContainer>
  );
}

export default BgpMonitor;
