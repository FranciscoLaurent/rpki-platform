// ASN 详情页面
import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeftOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { getASNDetail } from '@/api/dashboard';
import type {
  ASNAlertItem,
  ASNPrefixItem,
} from '@/api/dashboard';

const { Text, Paragraph } = Typography;

/** 状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  inactive: 'default',
};

/** ASN 关系类型颜色映射 */
const ASN_TYPE_COLOR: Record<string, string> = {
  own: 'purple',
  customer: 'green',
  provider: 'blue',
  peer: 'cyan',
  ixp: 'gold',
  route_server: 'orange',
  scrubber: 'magenta',
};

/** 严重等级颜色映射 */
const SEVERITY_COLOR: Record<string, string> = {
  P0: 'red',
  P1: 'volcano',
  P2: 'orange',
  P3: 'gold',
  P4: 'blue',
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

/** 重要度颜色映射 */
const IMPORTANCE_COLOR: Record<string, string> = {
  critical: 'red',
  important: 'orange',
  normal: 'blue',
  low: 'default',
};

/** ASN 详情页面 */
function ASNDetail() {
  const navigate = useNavigate();
  const { asn_id: asnIdStr } = useParams<{ asn_id: string }>();
  const asnId = asnIdStr ? Number(asnIdStr) : NaN;

  /** 拉取 ASN 详情数据 */
  const { data, isLoading, isFetching, refetch, error } = useQuery({
    queryKey: ['asn-detail', asnId],
    queryFn: () => getASNDetail(asnId),
    enabled: !Number.isNaN(asnId),
    refetchInterval: 60_000,
  });

  /** 关联前缀表格列定义 */
  const prefixColumns: ColumnsType<ASNPrefixItem> = useMemo(
    () => [
      {
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
        width: 80,
      },
      {
        title: '前缀',
        dataIndex: 'prefix',
        key: 'prefix',
        render: (v: string) => <Text code strong>{v}</Text>,
      },
      {
        title: '协议族',
        dataIndex: 'prefix_family',
        key: 'prefix_family',
        width: 100,
        render: (v: number) => <Tag color="blue">{v === 4 ? 'IPv4' : 'IPv6'}</Tag>,
      },
      {
        title: '前缀长度',
        dataIndex: 'prefix_length',
        key: 'prefix_length',
        width: 100,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>,
      },
      {
        title: '重要度',
        dataIndex: 'importance',
        key: 'importance',
        width: 100,
        render: (v: string) => (
          <Tag color={IMPORTANCE_COLOR[v] || 'default'}>{v}</Tag>
        ),
      },
      {
        title: '业务归属',
        dataIndex: 'business_service',
        key: 'business_service',
        render: (v: string | null) => v || '-',
      },
    ],
    [],
  );

  /** 告警表格列定义 */
  const alertColumns: ColumnsType<ASNAlertItem> = useMemo(
    () => [
      {
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
        width: 80,
      },
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
        width: 100,
        render: (v: string) => <Tag color={SEVERITY_COLOR[v] || 'default'}>{v}</Tag>,
      },
      {
        title: '关联前缀',
        dataIndex: 'prefix',
        key: 'prefix',
        width: 180,
        render: (v: string) => <Text code>{v}</Text>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 110,
        render: (v: string) => (
          <Tag color={ALERT_STATUS_COLOR[v] || 'default'}>{v}</Tag>
        ),
      },
      {
        title: '风险评分',
        dataIndex: 'risk_score',
        key: 'risk_score',
        width: 100,
        render: (v: number) => (
          <Text strong style={{ color: v >= 70 ? '#cf1322' : v >= 40 ? '#fa8c16' : '#52c41a' }}>
            {v.toFixed(1)}
          </Text>
        ),
      },
      {
        title: '最近发现',
        dataIndex: 'last_seen_at',
        key: 'last_seen_at',
        width: 180,
        render: (v: string | null) =>
          v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
      },
    ],
    [],
  );

  /** 渲染加载中 */
  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="加载 ASN 详情..." />
      </div>
    );
  }

  /** 渲染错误 */
  if (error || !data) {
    return (
      <PageContainer
        title="ASN 详情"
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
          description={(error as Error)?.message || 'ASN 不存在或无访问权限'}
          action={
            <Button size="small" onClick={() => refetch()}>
              重试
            </Button>
          }
        />
      </PageContainer>
    );
  }

  const { asset } = data;

  return (
    <PageContainer
      title={`ASN 详情：AS${asset.asn} (${asset.name})`}
      subtitle="展示 ASN 基本信息、关联前缀、上下游关系、异常记录与风险画像"
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
      {/* 顶部：ASN 基本信息 */}
      <Card title="ASN 基本信息" bodyStyle={{ padding: 24 }} style={{ marginBottom: 16 }}>
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }} size="small">
          <Descriptions.Item label="ASN">
            <Text strong>AS{asset.asn}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="名称">{asset.name}</Descriptions.Item>
          <Descriptions.Item label="关系类型">
            <Tag color={ASN_TYPE_COLOR[asset.asn_type] || 'default'}>
              {asset.asn_type}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[asset.status] || 'default'}>{asset.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="联系人">{asset.contact_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{asset.contact_email || '-'}</Descriptions.Item>
          <Descriptions.Item label="NOC 电话">{asset.noc_phone || '-'}</Descriptions.Item>
          <Descriptions.Item label="紧急联系">
            {asset.emergency_contact || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="关系标签">
            {asset.relationship_tags && asset.relationship_tags.length ? (
              <Space size={4} wrap>
                {asset.relationship_tags.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
              </Space>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {dayjs(asset.created_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间">
            {dayjs(asset.updated_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={4}>
            {asset.description || '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Tab 区域 */}
      <Card bodyStyle={{ padding: 24 }}>
        <Tabs
          defaultActiveKey="prefixes"
          items={[
            {
              key: 'prefixes',
              label: `关联前缀 (${data.related_prefixes.length})`,
              children: (
                <Table
                  rowKey="id"
                  columns={prefixColumns}
                  dataSource={data.related_prefixes}
                  pagination={{ pageSize: 10, size: 'small' }}
                  size="small"
                  scroll={{ x: 1000 }}
                  locale={{
                    emptyText: <Empty description="暂无关联前缀" />,
                  }}
                />
              ),
            },
            {
              key: 'alerts',
              label: `异常记录 (${data.alerts.length})`,
              children: (
                <Table
                  rowKey="id"
                  columns={alertColumns}
                  dataSource={data.alerts}
                  pagination={{ pageSize: 10, size: 'small' }}
                  size="small"
                  scroll={{ x: 1200 }}
                  locale={{
                    emptyText: <Empty description="暂无异常记录" />,
                  }}
                />
              ),
            },
            {
              key: 'risk',
              label: '风险画像',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Card type="inner" title="风险画像描述">
                    {data.risk_profile ? (
                      <Paragraph>{data.risk_profile}</Paragraph>
                    ) : (
                      <Empty description="暂无风险画像" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </Card>
                  <Card type="inner" title="AS 关系（占位，待 BGP AS_PATH 分析实现）">
                    <Descriptions column={3} size="small" bordered>
                      <Descriptions.Item label="上游 AS">
                        {data.upstream.length ? (
                          <Space size={4} wrap>
                            {data.upstream.map((asn) => (
                              <Tag key={asn} color="blue">AS{asn}</Tag>
                            ))}
                          </Space>
                        ) : (
                          <Text type="secondary">暂无数据</Text>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label="下游 AS">
                        {data.downstream.length ? (
                          <Space size={4} wrap>
                            {data.downstream.map((asn) => (
                              <Tag key={asn} color="green">AS{asn}</Tag>
                            ))}
                          </Space>
                        ) : (
                          <Text type="secondary">暂无数据</Text>
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label="对等 AS">
                        {data.peers.length ? (
                          <Space size={4} wrap>
                            {data.peers.map((asn) => (
                              <Tag key={asn} color="cyan">AS{asn}</Tag>
                            ))}
                          </Space>
                        ) : (
                          <Text type="secondary">暂无数据</Text>
                        )}
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                  <Card type="inner" title="历史路径（占位，待 ClickHouse 历史数据接入）">
                    {data.history_paths.length ? (
                      <Text>{JSON.stringify(data.history_paths)}</Text>
                    ) : (
                      <Empty description="暂无历史路径数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </Card>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </PageContainer>
  );
}

export default ASNDetail;
