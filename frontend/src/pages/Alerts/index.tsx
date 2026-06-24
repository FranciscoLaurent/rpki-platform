// 告警事件页面：检测规则 / 告警 / 事件
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Empty,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import {
  getAlerts,
  getDetectionRules,
  getIncidents,
} from '@/api/detection';
import type {
  Alert,
  DetectionRule,
  Incident,
} from '@/api/detection';

/** 严重等级颜色映射 */
const SEVERITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'volcano',
  P2: 'orange',
  P3: 'gold',
  P4: 'blue',
};

/** 告警/事件状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  open: 'red',
  acknowledged: 'orange',
  resolved: 'green',
  closed: 'default',
};

/** 告警/事件状态标签映射 */
const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  acknowledged: '已确认',
  resolved: '已解决',
  closed: '已关闭',
};

/** 告警状态过滤选项 */
const ALERT_STATUS_OPTIONS = [
  { label: '全部状态', value: 'all' },
  { label: '待处理', value: 'open' },
  { label: '已确认', value: 'acknowledged' },
  { label: '已解决', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
];

/** 单页条数 */
const PAGE_SIZE = 10;

/** 告警事件页面 */
function Alerts() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'rules' | 'alerts' | 'incidents'>('rules');
  const [alertStatus, setAlertStatus] = useState<string>('all');
  const [alertPage, setAlertPage] = useState(1);
  const [incidentPage, setIncidentPage] = useState(1);

  /** 拉取检测规则列表 */
  const rulesQuery = useQuery({
    queryKey: ['detection-rules'],
    queryFn: () => getDetectionRules({ limit: 500 }),
    enabled: activeTab === 'rules',
  });

  /** 拉取告警列表 */
  const alertsQuery = useQuery({
    queryKey: ['detection-alerts', alertStatus],
    queryFn: () =>
      getAlerts({
        status: alertStatus === 'all' ? undefined : alertStatus,
        limit: 500,
      }),
    enabled: activeTab === 'alerts',
  });

  /** 拉取事件列表 */
  const incidentsQuery = useQuery({
    queryKey: ['detection-incidents'],
    queryFn: () => getIncidents({ limit: 500 }),
    enabled: activeTab === 'incidents',
  });

  /** 检测规则表格列定义 */
  const ruleColumns: ColumnsType<DetectionRule> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '编码',
      dataIndex: 'code',
      key: 'code',
      width: 180,
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'rule_type',
      key: 'rule_type',
      width: 140,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '严重等级',
      dataIndex: 'severity',
      key: 'severity',
      width: 110,
      render: (v: string) => (
        <Tag color={SEVERITY_COLOR[v] ?? 'default'}>{v}</Tag>
      ),
    },
    {
      title: '启用状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      align: 'center' as const,
      render: (v: boolean) => <Switch checked={v} size="small" />,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 90,
      align: 'center' as const,
    },
  ];

  /** 告警表格列定义 */
  const alertColumns: ColumnsType<Alert> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 140,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '严重等级',
      dataIndex: 'severity',
      key: 'severity',
      width: 110,
      render: (v: string) => (
        <Tag color={SEVERITY_COLOR[v] ?? 'default'}>{v}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={STATUS_COLOR[v] ?? 'default'}>
          {STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      width: 180,
      ellipsis: true,
    },
    {
      title: '起源 AS',
      dataIndex: 'origin_as',
      key: 'origin_as',
      width: 100,
      align: 'center' as const,
      render: (v: number | null) => (v != null ? `AS${v}` : '-'),
    },
    {
      title: '风险评分',
      dataIndex: 'risk_score',
      key: 'risk_score',
      width: 100,
      align: 'center' as const,
      render: (v: number) => (
        <Tag color={v >= 70 ? 'red' : v >= 40 ? 'orange' : 'default'}>
          {v}
        </Tag>
      ),
    },
    {
      title: '首次出现',
      dataIndex: 'first_seen_at',
      key: 'first_seen_at',
      width: 170,
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '最后出现',
      dataIndex: 'last_seen_at',
      key: 'last_seen_at',
      width: 170,
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
  ];

  /** 事件表格列定义 */
  const incidentColumns: ColumnsType<Incident> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: '严重等级',
      dataIndex: 'severity',
      key: 'severity',
      width: 110,
      render: (v: string) => (
        <Tag color={SEVERITY_COLOR[v] ?? 'default'}>{v}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={STATUS_COLOR[v] ?? 'default'}>
          {STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '影响前缀',
      dataIndex: 'affected_prefixes',
      key: 'affected_prefixes',
      width: 200,
      render: (v: string[] | null) =>
        v && v.length ? (
          <Space size={4} wrap>
            {v.slice(0, 3).map((p, i) => (
              <Tag key={i}>{p}</Tag>
            ))}
            {v.length > 3 ? <Tag>+{v.length - 3}</Tag> : null}
          </Space>
        ) : (
          '-'
        ),
    },
    {
      title: '影响 ASN',
      dataIndex: 'affected_asns',
      key: 'affected_asns',
      width: 160,
      render: (v: number[] | null) =>
        v && v.length ? (
          <Space size={4} wrap>
            {v.slice(0, 3).map((asn, i) => (
              <Tag key={i}>AS{asn}</Tag>
            ))}
            {v.length > 3 ? <Tag>+{v.length - 3}</Tag> : null}
          </Space>
        ) : (
          '-'
        ),
    },
    {
      title: '首次出现',
      dataIndex: 'first_seen_at',
      key: 'first_seen_at',
      width: 170,
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '最后出现',
      dataIndex: 'last_seen_at',
      key: 'last_seen_at',
      width: 170,
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
  ];

  return (
    <PageContainer
      title="告警事件"
      subtitle="管理路由安全检测规则、告警与事件处置"
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as typeof activeTab)}
        items={[
          {
            key: 'rules',
            label: '检测规则',
            children: (
              <Spin spinning={rulesQuery.isLoading}>
                <Table<DetectionRule>
                  rowKey="id"
                  columns={ruleColumns}
                  dataSource={rulesQuery.data ?? []}
                  pagination={{ pageSize: PAGE_SIZE, size: 'small' }}
                  size="small"
                  locale={{
                    emptyText: <Empty description="暂无检测规则" />,
                  }}
                />
              </Spin>
            ),
          },
          {
            key: 'alerts',
            label: '告警',
            children: (
              <Spin spinning={alertsQuery.isLoading}>
                <div style={{ marginBottom: 16 }}>
                  <Space>
                    <span>状态：</span>
                    <Select
                      value={alertStatus}
                      onChange={(v) => {
                        setAlertStatus(v);
                        setAlertPage(1);
                      }}
                      options={ALERT_STATUS_OPTIONS}
                      style={{ width: 160 }}
                    />
                  </Space>
                </div>
                <Table<Alert>
                  rowKey="id"
                  columns={alertColumns}
                  dataSource={alertsQuery.data ?? []}
                  pagination={{
                    current: alertPage,
                    pageSize: PAGE_SIZE,
                    size: 'small',
                    onChange: (page) => setAlertPage(page),
                  }}
                  size="small"
                  locale={{
                    emptyText: <Empty description="暂无告警" />,
                  }}
                />
              </Spin>
            ),
          },
          {
            key: 'incidents',
            label: '事件',
            children: (
              <Spin spinning={incidentsQuery.isLoading}>
                <Table<Incident>
                  rowKey="id"
                  columns={incidentColumns}
                  dataSource={incidentsQuery.data ?? []}
                  pagination={{
                    current: incidentPage,
                    pageSize: PAGE_SIZE,
                    size: 'small',
                    onChange: (page) => setIncidentPage(page),
                  }}
                  size="small"
                  onRow={(record) => ({
                    onClick: () => navigate(`/incidents/${record.id}`),
                    style: { cursor: 'pointer' },
                  })}
                  locale={{
                    emptyText: <Empty description="暂无事件" />,
                  }}
                />
              </Spin>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}

export default Alerts;
