// 事件详情时间线页面
import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  List,
  Row,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { getIncidentTimeline } from '@/api/dashboard';
import type { IncidentTimelineItem } from '@/api/dashboard';

const { Text, Paragraph } = Typography;

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

/** 事件状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  open: 'red',
  investigating: 'orange',
  mitigating: 'gold',
  resolved: 'green',
  closed: 'default',
};

/** 事件状态标签映射 */
const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  investigating: '调查中',
  mitigating: '处置中',
  resolved: '已恢复',
  closed: '已关闭',
};

/** 时间线事件类型颜色映射 */
const TIMELINE_COLOR: Record<string, string> = {
  first_seen: 'blue',
  created: 'blue',
  alert: 'orange',
  propagation: 'gold',
  confirmed: 'cyan',
  assigned: 'cyan',
  escalated: 'orange',
  updated: 'blue',
  mitigating: 'gold',
  resolved: 'green',
  closed: 'gray',
  unknown: 'blue',
};

/** 时间线事件类型图标映射 */
const TIMELINE_ICON: Record<string, React.ReactNode> = {
  first_seen: <ClockCircleOutlined />,
  created: <ClockCircleOutlined />,
  alert: <ExclamationCircleOutlined />,
  confirmed: <CheckCircleOutlined />,
  assigned: <CheckCircleOutlined />,
  resolved: <CheckCircleOutlined />,
  closed: <CheckCircleOutlined />,
};

/** 时间线事件类型标签映射 */
const TIMELINE_LABEL: Record<string, string> = {
  first_seen: '首次出现',
  created: '事件创建',
  alert: '告警生成',
  propagation: '传播变化',
  confirmed: '人工确认',
  assigned: '事件分派',
  escalated: '事件升级',
  updated: '事件更新',
  mitigating: '处置中',
  resolved: '事件恢复',
  closed: '事件关闭',
  unknown: '其他',
};

/** 告警状态颜色映射 */
const ALERT_STATUS_COLOR: Record<string, string> = {
  new: 'red',
  confirmed: 'orange',
  assigned: 'gold',
  resolved: 'green',
  closed: 'default',
  false_positive: 'default',
};

/** 事件详情时间线页面 */
function IncidentDetail() {
  const navigate = useNavigate();
  const { incident_id: incidentIdStr } = useParams<{ incident_id: string }>();
  const incidentId = incidentIdStr ? Number(incidentIdStr) : NaN;

  /** 拉取事件时间线数据 */
  const { data, isLoading, isFetching, refetch, error } = useQuery({
    queryKey: ['incident-timeline', incidentId],
    queryFn: () => getIncidentTimeline(incidentId),
    enabled: !Number.isNaN(incidentId),
    refetchInterval: 60_000,
  });

  /** 时间线条目（按时间排序） */
  const timelineItems = useMemo(() => {
    if (!data?.timeline?.length) return [];
    return data.timeline
      .slice()
      .sort((a, b) => dayjs(a.timestamp).valueOf() - dayjs(b.timestamp).valueOf());
  }, [data?.timeline]);

  /** 渲染加载中 */
  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="加载事件时间线..." />
      </div>
    );
  }

  /** 渲染错误 */
  if (error || !data) {
    return (
      <PageContainer
        title="事件详情"
        extra={
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
          >
            返回
          </Button>
        }
      >
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={(error as Error)?.message || '事件不存在或无访问权限'}
          action={
            <Button size="small" onClick={() => refetch()}>
              重试
            </Button>
          }
        />
      </PageContainer>
    );
  }

  const { incident, impact_scope, recommendations, root_cause_analysis } = data;

  return (
    <PageContainer
      title={`事件详情：${incident.title}`}
      subtitle="展示事件完整生命周期，包括首次出现、传播变化、告警、人工确认、处置、恢复与关闭"
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            loading={isFetching}
          >
            刷新
          </Button>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
            返回
          </Button>
        </Space>
      }
    >
      {/* 顶部：事件基本信息 */}
      <Card title="事件基本信息" bodyStyle={{ padding: 24 }} style={{ marginBottom: 16 }}>
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }} size="small">
          <Descriptions.Item label="事件 ID">{incident.id}</Descriptions.Item>
          <Descriptions.Item label="标题" span={3}>
            <Text strong>{incident.title}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="严重等级">
            <Tag color={SEVERITY_COLOR[incident.severity] || 'default'}>
              {SEVERITY_LABEL[incident.severity] || incident.severity}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[incident.status] || 'default'}>
              {STATUS_LABEL[incident.status] || incident.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="分派给">
            {incident.assigned_to ? `用户 ${incident.assigned_to}` : '未分派'}
          </Descriptions.Item>
          <Descriptions.Item label="关联告警数">
            {data.related_alerts?.length ?? 0}
          </Descriptions.Item>
          <Descriptions.Item label="首次发现">
            {incident.first_seen_at
              ? dayjs(incident.first_seen_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="最近发现">
            {incident.last_seen_at
              ? dayjs(incident.last_seen_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="恢复时间">
            {incident.resolved_at
              ? dayjs(incident.resolved_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="关闭时间">
            {incident.closed_at
              ? dayjs(incident.closed_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {dayjs(incident.created_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间">
            {dayjs(incident.updated_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="受影响前缀" span={2}>
            {incident.affected_prefixes && incident.affected_prefixes.length ? (
              <Space size={4} wrap>
                {incident.affected_prefixes.map((p) => (
                  <Tag key={p} color="blue">
                    <Text code style={{ color: 'inherit' }}>{p}</Text>
                  </Tag>
                ))}
              </Space>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="受影响 ASN" span={2}>
            {incident.affected_asns && incident.affected_asns.length ? (
              <Space size={4} wrap>
                {incident.affected_asns.map((asn) => (
                  <Tag key={asn} color="purple">AS{asn}</Tag>
                ))}
              </Space>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={4}>
            {incident.description || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="根因分析" span={4}>
            {incident.root_cause || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="处置结论" span={4}>
            {incident.resolution || '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 主体：时间线 + 侧边详情 */}
      <Row gutter={[16, 16]}>
        {/* 左侧：时间线 */}
        <Col xs={24} lg={16}>
          <Card title="事件时间线" bodyStyle={{ padding: 24 }}>
            {timelineItems.length === 0 ? (
              <Empty description="暂无时间线数据" />
            ) : (
              <Timeline
                mode="left"
                items={timelineItems.map((item: IncidentTimelineItem) => ({
                  color: TIMELINE_COLOR[item.event_type] || 'blue',
                  icon: TIMELINE_ICON[item.event_type],
                  label: (
                    <div>
                      <Text strong>
                        {dayjs(item.timestamp).format('YYYY-MM-DD HH:mm:ss')}
                      </Text>
                      <div>
                        <Tag color={TIMELINE_COLOR[item.event_type] || 'blue'}>
                          {TIMELINE_LABEL[item.event_type] || item.event_type}
                        </Tag>
                      </div>
                    </div>
                  ),
                  children: (
                    <div style={{ paddingBottom: 8 }}>
                      <Paragraph style={{ margin: 0 }}>{item.description}</Paragraph>
                      {item.operator && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          操作人：{item.operator}
                        </Text>
                      )}
                    </div>
                  ),
                }))}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：事件详情 */}
        <Col xs={24} lg={8}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {/* 影响范围 */}
            <Card title="影响范围" bodyStyle={{ padding: 24 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="受影响前缀数">
                  <Text strong>
                    {(impact_scope?.affected_prefixes as string[] | undefined)?.length ?? 0}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="受影响 ASN 数">
                  <Text strong>
                    {(impact_scope?.affected_asns as number[] | undefined)?.length ?? 0}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="关联告警数">
                  <Text strong>
                    {(impact_scope?.alert_count as number | undefined) ?? 0}
                  </Text>
                </Descriptions.Item>
              </Descriptions>
              {incident.affected_prefixes && incident.affected_prefixes.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    前缀列表：
                  </Text>
                  <div style={{ marginTop: 4 }}>
                    <Space size={4} wrap>
                      {incident.affected_prefixes.slice(0, 5).map((p) => (
                        <Tag key={p} color="blue">
                          <Text code style={{ color: 'inherit' }}>{p}</Text>
                        </Tag>
                      ))}
                      {incident.affected_prefixes.length > 5 && (
                        <Tag>+{incident.affected_prefixes.length - 5}</Tag>
                      )}
                    </Space>
                  </div>
                </div>
              )}
            </Card>

            {/* 根因分析 */}
            <Card title="根因分析" bodyStyle={{ padding: 24 }}>
              {root_cause_analysis ? (
                <Paragraph>{root_cause_analysis}</Paragraph>
              ) : (
                <Empty
                  description="暂无根因分析"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </Card>

            {/* 处置建议 */}
            <Card title="处置建议" bodyStyle={{ padding: 24 }}>
              {recommendations.length > 0 ? (
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  {recommendations.map((rec, idx) => {
                    const isHighRisk =
                      rec.includes('P0') ||
                      rec.includes('P1') ||
                      rec.includes('立即') ||
                      rec.includes('劫持');
                    const isWarning =
                      rec.includes('建议') && !isHighRisk && !rec.includes('正常');
                    return (
                      <Alert
                        key={idx}
                        type={isHighRisk ? 'error' : isWarning ? 'warning' : 'success'}
                        showIcon
                        icon={
                          isHighRisk ? (
                            <ExclamationCircleOutlined />
                          ) : isWarning ? (
                            <WarningOutlined />
                          ) : (
                            <CheckCircleOutlined />
                          )
                        }
                        message={rec}
                      />
                    );
                  })}
                </Space>
              ) : (
                <Empty
                  description="暂无处置建议"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </Card>
          </Space>
        </Col>
      </Row>

      {/* 关联告警列表 */}
      {data.related_alerts && data.related_alerts.length > 0 && (
        <Card title={`关联告警 (${data.related_alerts.length})`} bodyStyle={{ padding: 24 }} style={{ marginTop: 16 }}>
          <List
            bordered
            dataSource={data.related_alerts}
            renderItem={(alert: Record<string, unknown>, idx: number) => (
              <List.Item>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space>
                    <Tag color={SEVERITY_COLOR[(alert.severity as string) || 'P3'] || 'default'}>
                      {(alert.severity as string) || 'P3'}
                    </Tag>
                    <Tag color="blue">{(alert.alert_type as string) || '-'}</Tag>
                    <Tag color={ALERT_STATUS_COLOR[(alert.status as string) || 'new'] || 'default'}>
                      {(alert.status as string) || 'new'}
                    </Tag>
                    <Text strong>{(alert.title as string) || '-'}</Text>
                  </Space>
                  <Space size={16}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      前缀：<Text code>{(alert.prefix as string) || '-'}</Text>
                    </Text>
                    {alert.origin_as && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        Origin AS：AS{alert.origin_as as number}
                      </Text>
                    )}
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      风险评分：{((alert.risk_score as number) ?? 0).toFixed(1)}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      首次发现：
                      {alert.first_seen_at
                        ? dayjs(alert.first_seen_at as string).format('YYYY-MM-DD HH:mm:ss')
                        : '-'}
                    </Text>
                  </Space>
                </Space>
              </List.Item>
            )}
          />
        </Card>
      )}
    </PageContainer>
  );
}

export default IncidentDetail;
