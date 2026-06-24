// 总览驾驶舱页面
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Empty,
  List,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { getDashboardOverview } from '@/api/dashboard';
import type {
  DashboardOverview,
  RiskTrendPoint,
} from '@/api/dashboard';

const { Text, Title } = Typography;

/** 严重等级颜色映射 */
const SEVERITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'volcano',
  P2: 'orange',
  P3: 'gold',
  P4: 'blue',
};

/** 严重等级标签映射 */
const SEVERITY_LABEL: Record<string, string> = {
  P0: 'P0 紧急',
  P1: 'P1 高危',
  P2: 'P2 中危',
  P3: 'P3 低危',
  P4: 'P4 提示',
};

/** RPKI 缓存状态颜色映射 */
const CACHE_STATUS_COLOR: Record<string, string> = {
  healthy: 'green',
  stale: 'orange',
  unknown: 'default',
};

/** RPKI 缓存状态标签映射 */
const CACHE_STATUS_LABEL: Record<string, string> = {
  healthy: '健康',
  stale: '过期',
  unknown: '未知',
};

/** 验证状态颜色映射 */
const VALIDATION_COLOR: Record<string, string> = {
  valid: '#52c41a',
  invalid: '#ff4d4f',
  not_found: '#faad14',
};

/** 总览驾驶舱页面 */
function Dashboard() {
  /** 拉取驾驶舱数据，每 30 秒自动刷新 */
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: getDashboardOverview,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  /** 风险趋势最大值（用于折线图缩放） */
  const maxTrendValue = useMemo(() => {
    if (!data?.risk_trend?.length) return 0;
    return Math.max(
      ...data.risk_trend.map(
        (p: RiskTrendPoint) => p.alert_count + p.incident_count,
      ),
      1,
    );
  }, [data?.risk_trend]);

  /** 验证状态分布数据 */
  const validationData = useMemo(() => {
    if (!data) return [];
    const vd = data.validation_distribution;
    return [
      { key: 'valid', label: 'Valid', value: vd.valid, color: VALIDATION_COLOR.valid },
      { key: 'invalid', label: 'Invalid', value: vd.invalid, color: VALIDATION_COLOR.invalid },
      { key: 'not_found', label: 'NotFound', value: vd.not_found, color: VALIDATION_COLOR.not_found },
    ].filter((item) => item.value > 0);
  }, [data]);

  /** BGP 数据源列表 */
  const bgpSourceList = useMemo(() => {
    if (!data) return [];
    const byType = data.bgp_source_status.by_type || {};
    return Object.entries(byType).map(([type, count]) => ({
      key: type,
      type,
      count: count as number,
      active: data.bgp_source_status.active,
      error: data.bgp_source_status.error,
      total: data.bgp_source_status.total,
    }));
  }, [data]);

  /** 最近告警列表（从风险趋势中无法获取，使用事件统计模拟展示） */
  const recentAlerts = useMemo(() => {
    if (!data) return [];
    // 由于驾驶舱接口未直接返回告警列表，使用风险趋势数据展示
    return data.risk_trend
      .slice()
      .reverse()
      .map((p: RiskTrendPoint, idx: number) => ({
        key: idx,
        date: p.date,
        alert_count: p.alert_count,
        incident_count: p.incident_count,
      }))
      .filter((p) => p.alert_count > 0 || p.incident_count > 0);
  }, [data]);

  /** 表格列定义：最近告警 */
  const alertColumns: ColumnsType<typeof recentAlerts[number]> = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 140,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD'),
    },
    {
      title: '告警数',
      dataIndex: 'alert_count',
      key: 'alert_count',
      width: 100,
      render: (v: number) => (
        <Tag color={v > 0 ? 'orange' : 'default'}>{v}</Tag>
      ),
    },
    {
      title: '事件数',
      dataIndex: 'incident_count',
      key: 'incident_count',
      width: 100,
      render: (v: number) => (
        <Tag color={v > 0 ? 'red' : 'default'}>{v}</Tag>
      ),
    },
  ];

  /** 表格列定义：BGP 数据源 */
  const sourceColumns: ColumnsType<typeof bgpSourceList[number]> = [
    {
      title: '数据源类型',
      dataIndex: 'type',
      key: 'type',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '数量',
      dataIndex: 'count',
      key: 'count',
      width: 80,
      align: 'center' as const,
    },
  ];

  /** 渲染加载中 */
  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="加载驾驶舱数据..." />
      </div>
    );
  }

  const overview: DashboardOverview | undefined = data;

  return (
    <PageContainer
      title="总览驾驶舱"
      subtitle="实时展示 RPKI 安全管理平台关键指标与风险态势"
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            loading={isFetching}
          >
            刷新
          </Button>
        </Space>
      }
    >
      <Row gutter={[16, 16]}>
        {/* 顶部指标卡区域 */}
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="IP 前缀总数"
              value={overview?.prefix_stats.total ?? 0}
              prefix={<GlobalOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                活跃 {overview?.prefix_stats.active ?? 0} · IPv4{' '}
                {overview?.prefix_stats.by_family?.ipv4 ?? 0} · IPv6{' '}
                {overview?.prefix_stats.by_family?.ipv6 ?? 0}
              </Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="ASN 总数"
              value={overview?.asn_stats.total ?? 0}
              prefix={<DatabaseOutlined style={{ color: '#722ed1' }} />}
              valueStyle={{ color: '#722ed1' }}
            />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                自有 {overview?.asn_stats.by_type?.own ?? 0} · 客户{' '}
                {overview?.asn_stats.by_type?.customer ?? 0} · 对等{' '}
                {overview?.asn_stats.by_type?.peer ?? 0}
              </Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="ROA 覆盖率"
              value={((overview?.roa_coverage.coverage_rate ?? 0) * 100).toFixed(2)}
              precision={2}
              suffix="%"
              prefix={<SafetyCertificateOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
            <Progress
              percent={Math.round((overview?.roa_coverage.coverage_rate ?? 0) * 100)}
              size="small"
              status={
                (overview?.roa_coverage.coverage_rate ?? 0) >= 0.8
                  ? 'success'
                  : (overview?.roa_coverage.coverage_rate ?? 0) >= 0.5
                  ? 'normal'
                  : 'exception'
              }
              style={{ marginTop: 8, marginBottom: 0 }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              已覆盖 {overview?.roa_coverage.prefixes_with_roa ?? 0} /{' '}
              {overview?.roa_coverage.total_prefixes ?? 0} · 缺失{' '}
              {overview?.roa_coverage.missing_count ?? 0}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="活跃事件（P0/P1）"
              value={
                (overview?.incident_stats.p0 ?? 0) +
                (overview?.incident_stats.p1 ?? 0)
              }
              prefix={<AlertOutlined style={{ color: '#cf1322' }} />}
              valueStyle={{ color: '#cf1322' }}
            />
            <div style={{ marginTop: 8 }}>
              <Space size={4} wrap>
                <Tag color="red">P0 {overview?.incident_stats.p0 ?? 0}</Tag>
                <Tag color="volcano">P1 {overview?.incident_stats.p1 ?? 0}</Tag>
                <Tag color="orange">P2 {overview?.incident_stats.p2 ?? 0}</Tag>
                <Tag color="gold">P3 {overview?.incident_stats.p3 ?? 0}</Tag>
              </Space>
            </div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
              未关闭事件总数：{overview?.incident_stats.total_open ?? 0}
            </Text>
          </Card>
        </Col>
      </Row>

      {/* 中部图表区域 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 左侧：Valid/Invalid/NotFound 分布饼图（CSS 实现） */}
        <Col xs={24} lg={8}>
          <Card title="RPKI 验证状态分布" bodyStyle={{ padding: 24 }}>
            {validationData.length === 0 ? (
              <Empty description="暂无验证数据" />
            ) : (
              <div>
                {/* 简单饼图：使用 conic-gradient 实现 */}
                <div
                  style={{
                    width: 200,
                    height: 200,
                    margin: '0 auto 16px',
                    borderRadius: '50%',
                    background: _buildConicGradient(validationData),
                    position: 'relative',
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      width: 110,
                      height: 110,
                      borderRadius: '50%',
                      background: '#fff',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Title level={4} style={{ margin: 0 }}>
                      {overview?.validation_distribution.total ?? 0}
                    </Title>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      公告总数
                    </Text>
                  </div>
                </div>
                <Row justify="center" gutter={[24, 8]}>
                  {validationData.map((item) => (
                    <Col key={item.key} style={{ textAlign: 'center' }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 6,
                        }}
                      >
                        <span
                          style={{
                            display: 'inline-block',
                            width: 12,
                            height: 12,
                            borderRadius: 2,
                            background: item.color,
                          }}
                        />
                        <Text strong>{item.label}</Text>
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: item.color }}>
                        {item.value}
                      </div>
                    </Col>
                  ))}
                </Row>
              </div>
            )}
          </Card>
        </Col>

        {/* 中间：风险趋势折线图（CSS 实现） */}
        <Col xs={24} lg={8}>
          <Card title="最近 7 天风险趋势" bodyStyle={{ padding: 24 }}>
            {!overview?.risk_trend?.length ? (
              <Empty description="暂无趋势数据" />
            ) : (
              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'flex-end',
                    justifyContent: 'space-between',
                    height: 200,
                    padding: '0 8px',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                >
                  {overview.risk_trend.map((point: RiskTrendPoint) => {
                    const total = point.alert_count + point.incident_count;
                    const heightPct = (total / maxTrendValue) * 100;
                    const alertPct =
                      total > 0 ? (point.alert_count / total) * 100 : 0;
                    const incidentPct = 100 - alertPct;
                    return (
                      <div
                        key={point.date}
                        style={{
                          flex: 1,
                          margin: '0 4px',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          height: '100%',
                          justifyContent: 'flex-end',
                        }}
                        title={`${point.date}\n告警：${point.alert_count}\n事件：${point.incident_count}`}
                      >
                        <Text style={{ fontSize: 11, marginBottom: 4 }}>
                          {total}
                        </Text>
                        <div
                          style={{
                            width: '60%',
                            minWidth: 16,
                            height: `${Math.max(heightPct, 2)}%`,
                            display: 'flex',
                            flexDirection: 'column',
                            borderRadius: 4,
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: '100%',
                              height: `${incidentPct}%`,
                              background: '#ff4d4f',
                              minHeight: point.incident_count > 0 ? 2 : 0,
                            }}
                          />
                          <div
                            style={{
                              width: '100%',
                              height: `${alertPct}%`,
                              background: '#faad14',
                              minHeight: point.alert_count > 0 ? 2 : 0,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '4px 8px 0',
                  }}
                >
                  {overview.risk_trend.map((point: RiskTrendPoint) => (
                    <Text
                      key={point.date}
                      type="secondary"
                      style={{ fontSize: 11, flex: 1, textAlign: 'center' }}
                    >
                      {dayjs(point.date).format('MM-DD')}
                    </Text>
                  ))}
                </div>
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <Space split={<span style={{ color: '#ccc' }}>|</span>}>
                    <span>
                      <span
                        style={{
                          display: 'inline-block',
                          width: 10,
                          height: 10,
                          background: '#faad14',
                          marginRight: 4,
                        }}
                      />
                      告警
                    </span>
                    <span>
                      <span
                        style={{
                          display: 'inline-block',
                          width: 10,
                          height: 10,
                          background: '#ff4d4f',
                          marginRight: 4,
                        }}
                      />
                      事件
                    </span>
                  </Space>
                </div>
              </div>
            )}
          </Card>
        </Col>

        {/* 右侧：BGP 数据源状态列表 */}
        <Col xs={24} lg={8}>
          <Card
            title="BGP 数据源状态"
            bodyStyle={{ padding: 0 }}
            extra={
              <Space>
                <Tag color="green">
                  <CheckCircleOutlined /> 活跃 {overview?.bgp_source_status.active ?? 0}
                </Tag>
                <Tag color="red">
                  <WarningOutlined /> 异常 {overview?.bgp_source_status.error ?? 0}
                </Tag>
              </Space>
            }
          >
            <Table
              rowKey="key"
              columns={sourceColumns}
              dataSource={bgpSourceList}
              pagination={false}
              size="small"
              locale={{ emptyText: <Empty description="暂无数据源" /> }}
            />
            <div style={{ padding: 12, borderTop: '1px solid #f0f0f0' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                数据源总数：{overview?.bgp_source_status.total ?? 0}
              </Text>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 底部区域 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* RPKI cache 状态 */}
        <Col xs={24} lg={8}>
          <Card title="RPKI 缓存状态" bodyStyle={{ padding: 24 }}>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic
                  title="缓存实例数"
                  value={overview?.rpki_cache_status.cache_count ?? 0}
                  prefix={<DatabaseOutlined />}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="VRP 总数"
                  value={overview?.rpki_cache_status.vrp_count ?? 0}
                  prefix={<SafetyCertificateOutlined />}
                />
              </Col>
              <Col span={12}>
                <div style={{ marginBottom: 4 }}>
                  <Text type="secondary">整体状态</Text>
                </div>
                <Tag
                  color={
                    CACHE_STATUS_COLOR[overview?.rpki_cache_status.status ?? 'unknown']
                  }
                  style={{ fontSize: 14, padding: '4px 12px' }}
                >
                  {CACHE_STATUS_LABEL[overview?.rpki_cache_status.status ?? 'unknown']}
                </Tag>
              </Col>
              <Col span={12}>
                <div style={{ marginBottom: 4 }}>
                  <Text type="secondary">最后更新</Text>
                </div>
                <Text>
                  {overview?.rpki_cache_status.last_update
                    ? dayjs(overview.rpki_cache_status.last_update).format(
                        'YYYY-MM-DD HH:mm:ss',
                      )
                    : '-'}
                </Text>
              </Col>
            </Row>
          </Card>
        </Col>

        {/* 最近告警列表 */}
        <Col xs={24} lg={16}>
          <Card
            title="最近风险动态"
            bodyStyle={{ padding: 0 }}
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                最近 7 天
              </Text>
            }
          >
            <Table
              rowKey="key"
              columns={alertColumns}
              dataSource={recentAlerts}
              pagination={{ pageSize: 10, size: 'small' }}
              size="small"
              locale={{ emptyText: <Empty description="暂无风险动态" /> }}
            />
          </Card>
        </Col>
      </Row>

      {/* 事件严重等级分布 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="事件严重等级分布" bodyStyle={{ padding: 24 }}>
            <List
              grid={{
                gutter: 16,
                xs: 1,
                sm: 2,
                md: 5,
                lg: 5,
                xl: 5,
                xxl: 5,
              }}
              dataSource={[
                { key: 'P0', count: overview?.incident_stats.p0 ?? 0 },
                { key: 'P1', count: overview?.incident_stats.p1 ?? 0 },
                { key: 'P2', count: overview?.incident_stats.p2 ?? 0 },
                { key: 'P3', count: overview?.incident_stats.p3 ?? 0 },
                { key: 'P4', count: overview?.incident_stats.p4 ?? 0 },
              ]}
              renderItem={(item) => (
                <List.Item>
                  <Card
                    bodyStyle={{ padding: 16, textAlign: 'center' }}
                    style={{
                      borderTop: `3px solid ${
                        item.key === 'P0'
                          ? '#ff4d4f'
                          : item.key === 'P1'
                          ? '#fa541c'
                          : item.key === 'P2'
                          ? '#fa8c16'
                          : item.key === 'P3'
                          ? '#faad14'
                          : '#1890ff'
                      }`,
                    }}
                  >
                    <Tag
                      color={SEVERITY_COLOR[item.key]}
                      style={{ fontSize: 14, padding: '2px 8px', marginBottom: 8 }}
                    >
                      {SEVERITY_LABEL[item.key]}
                    </Tag>
                    <div style={{ fontSize: 24, fontWeight: 600 }}>
                      {item.count}
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      个事件
                    </Text>
                  </Card>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {/* 风险趋势时间线（辅助视图） */}
      {overview?.risk_trend?.length ? (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card title="风险趋势时间线" bodyStyle={{ padding: 24 }}>
              <Timeline
                items={overview.risk_trend
                  .filter((p: RiskTrendPoint) => p.alert_count > 0 || p.incident_count > 0)
                  .map((p: RiskTrendPoint) => ({
                    color:
                      p.incident_count > 0
                        ? 'red'
                        : p.alert_count > 5
                        ? 'orange'
                        : 'blue',
                    children: (
                      <div>
                        <Text strong>{dayjs(p.date).format('YYYY-MM-DD')}</Text>
                        <div style={{ marginTop: 4 }}>
                          <Tag color="orange">告警 {p.alert_count}</Tag>
                          <Tag color="red">事件 {p.incident_count}</Tag>
                        </div>
                      </div>
                    ),
                  }))}
              />
            </Card>
          </Col>
        </Row>
      ) : null}
    </PageContainer>
  );
}

/** 构建 conic-gradient 字符串，用于简单饼图渲染 */
function _buildConicGradient(
  data: Array<{ key: string; value: number; color: string }>,
): string {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) {
    return '#f0f0f0';
  }
  let current = 0;
  const segments: string[] = [];
  for (const item of data) {
    const start = (current / total) * 360;
    current += item.value;
    const end = (current / total) * 360;
    segments.push(`${item.color} ${start}deg ${end}deg`);
  }
  return `conic-gradient(${segments.join(', ')})`;
}

export default Dashboard;
