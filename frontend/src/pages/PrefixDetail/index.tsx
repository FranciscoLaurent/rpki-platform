// 前缀详情页面
import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  List,
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
import { getPrefixDetail } from '@/api/dashboard';
import type {
  AuthorizedOrigin,
  CurrentAnnouncement,
  MatchedVRP,
  PrefixAlertItem,
} from '@/api/dashboard';

const { Text, Title } = Typography;

/** 状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  inactive: 'default',
  reserved: 'blue',
  deprecated: 'default',
  valid: 'green',
  expired: 'orange',
  revoked: 'red',
};

/** 重要度颜色映射 */
const IMPORTANCE_COLOR: Record<string, string> = {
  critical: 'red',
  important: 'orange',
  normal: 'blue',
  low: 'default',
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

/** RPKI 验证状态颜色映射 */
const RPKI_STATUS_COLOR: Record<string, string> = {
  valid: 'green',
  invalid: 'red',
  not_found: 'orange',
};

/** 前缀详情页面 */
function PrefixDetail() {
  const navigate = useNavigate();
  const { prefix_id: prefixIdStr } = useParams<{ prefix_id: string }>();
  const prefixId = prefixIdStr ? Number(prefixIdStr) : NaN;

  /** 拉取前缀详情数据 */
  const { data, isLoading, isFetching, refetch, error } = useQuery({
    queryKey: ['prefix-detail', prefixId],
    queryFn: () => getPrefixDetail(prefixId),
    enabled: !Number.isNaN(prefixId),
    refetchInterval: 60_000,
  });

  /** 当前公告表格列定义 */
  const announcementColumns: ColumnsType<CurrentAnnouncement> = useMemo(
    () => [
      {
        title: 'ID',
        dataIndex: 'id',
        key: 'id',
        width: 80,
      },
      {
        title: '起源 AS',
        dataIndex: 'origin_as',
        key: 'origin_as',
        width: 120,
        render: (v: number | null) => (v ? <Text strong>AS{v}</Text> : '-'),
      },
      {
        title: 'AS_PATH',
        dataIndex: 'as_path',
        key: 'as_path',
        render: (v: number[] | null) =>
          v && v.length ? (
            <Space size={4} wrap>
              {v.map((asn, idx) => (
                <span key={idx}>
                  <Tag color="blue">AS{asn}</Tag>
                  {idx < v.length - 1 ? <span style={{ color: '#ccc' }}>→</span> : null}
                </span>
              ))}
            </Space>
          ) : (
            '-'
          ),
      },
      {
        title: '下一跳',
        dataIndex: 'next_hop',
        key: 'next_hop',
        width: 140,
        render: (v: string | null) => v || '-',
      },
      {
        title: 'RPKI 验证',
        dataIndex: 'rpki_validation_status',
        key: 'rpki_validation_status',
        width: 120,
        render: (v: string | null) =>
          v ? (
            <Tag color={RPKI_STATUS_COLOR[v] || 'default'}>{v}</Tag>
          ) : (
            <Tag>未验证</Tag>
          ),
      },
      {
        title: '观测时间',
        dataIndex: 'timestamp',
        key: 'timestamp',
        width: 180,
        render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
      },
    ],
    [],
  );

  /** ROA 表格列定义 */
  const roaColumns: ColumnsType<AuthorizedOrigin> = useMemo(
    () => [
      {
        title: 'ROA ID',
        dataIndex: 'roa_id',
        key: 'roa_id',
        width: 100,
      },
      {
        title: '授权 Origin AS',
        dataIndex: 'origin_as',
        key: 'origin_as',
        width: 140,
        render: (v: number) => <Text strong>AS{v}</Text>,
      },
      {
        title: '授权前缀',
        dataIndex: 'prefix',
        key: 'prefix',
        render: (v: string) => <Text code>{v}</Text>,
      },
      {
        title: '最大长度',
        dataIndex: 'max_length',
        key: 'max_length',
        width: 100,
        render: (v: number | null) => v ?? '-',
      },
      {
        title: 'TAL ID',
        dataIndex: 'tal_id',
        key: 'tal_id',
        width: 100,
        render: (v: number | null) => v ?? '-',
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>,
      },
      {
        title: '有效期',
        key: 'validity',
        width: 240,
        render: (_, record) => {
          if (!record.not_before && !record.not_after) return '-';
          return `${record.not_before ? dayjs(record.not_before).format('YYYY-MM-DD') : '-'} ~ ${
            record.not_after ? dayjs(record.not_after).format('YYYY-MM-DD') : '-'
          }`;
        },
      },
    ],
    [],
  );

  /** VRP 表格列定义 */
  const vrpColumns: ColumnsType<MatchedVRP> = useMemo(
    () => [
      {
        title: 'VRP ID',
        dataIndex: 'id',
        key: 'id',
        width: 100,
      },
      {
        title: '前缀',
        dataIndex: 'prefix',
        key: 'prefix',
        render: (v: string) => <Text code>{v}</Text>,
      },
      {
        title: 'Origin AS',
        dataIndex: 'origin_as',
        key: 'origin_as',
        width: 140,
        render: (v: number) => <Text strong>AS{v}</Text>,
      },
      {
        title: '最大长度',
        dataIndex: 'max_length',
        key: 'max_length',
        width: 100,
        render: (v: number | null) => v ?? '-',
      },
      {
        title: '信任锚',
        dataIndex: 'trust_anchor',
        key: 'trust_anchor',
        width: 140,
        render: (v: string | null) => v || '-',
      },
      {
        title: '验证状态',
        dataIndex: 'validation_status',
        key: 'validation_status',
        width: 120,
        render: (v: string) => <Tag color={RPKI_STATUS_COLOR[v] || 'default'}>{v}</Tag>,
      },
    ],
    [],
  );

  /** 告警表格列定义 */
  const alertColumns: ColumnsType<PrefixAlertItem> = useMemo(
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
        title: '置信度',
        dataIndex: 'confidence',
        key: 'confidence',
        width: 100,
        render: (v: number) => `${(v * 100).toFixed(0)}%`,
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
        <Spin size="large" tip="加载前缀详情..." />
      </div>
    );
  }

  /** 渲染错误 */
  if (error || !data) {
    return (
      <PageContainer
        title="前缀详情"
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
          description={(error as Error)?.message || '前缀不存在或无访问权限'}
          action={
            <Button size="small" onClick={() => refetch()}>
              重试
            </Button>
          }
        />
      </PageContainer>
    );
  }

  const { asset, recommendations } = data;

  return (
    <PageContainer
      title={`前缀详情：${asset.prefix}`}
      subtitle="展示前缀资产属性、合法 origin、当前公告、ROA/VRP 命中、告警与操作建议"
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
      {/* 顶部：前缀基本信息 */}
      <Card title="资产属性" bodyStyle={{ padding: 24 }} style={{ marginBottom: 16 }}>
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3, lg: 4 }} size="small">
          <Descriptions.Item label="前缀">
            <Text code strong>
              {asset.prefix}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="协议族">
            <Tag color="blue">{asset.prefix_family === 4 ? 'IPv4' : 'IPv6'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="前缀长度">{asset.prefix_length}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[asset.status] || 'default'}>{asset.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="重要度">
            <Tag color={IMPORTANCE_COLOR[asset.importance] || 'default'}>
              {asset.importance}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="业务归属">
            {asset.business_service || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="地域">{asset.region || '-'}</Descriptions.Item>
          <Descriptions.Item label="机房">{asset.site || '-'}</Descriptions.Item>
          <Descriptions.Item label="云区域">{asset.cloud_zone || '-'}</Descriptions.Item>
          <Descriptions.Item label="客户 ID">{asset.customer_id ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="标签">
            {asset.tags && asset.tags.length ? (
              <Space size={4} wrap>
                {asset.tags.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
              </Space>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="登记时间">
            {asset.registered_at
              ? dayjs(asset.registered_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="过期时间">
            {asset.expired_at
              ? dayjs(asset.expired_at).format('YYYY-MM-DD HH:mm:ss')
              : '-'}
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

      {/* 业务影响 */}
      <Card title="业务影响" bodyStyle={{ padding: 24 }} style={{ marginBottom: 16 }}>
        {data.business_impact ? (
          <Alert
            type="info"
            showIcon
            icon={<InfoCircleOutlined />}
            message={`关联业务：${data.business_impact}`}
            description="该前缀关联业务系统，路由异常可能直接影响业务可用性。"
          />
        ) : (
          <Empty description="未关联业务系统" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      {/* Tab 区域 */}
      <Card bodyStyle={{ padding: 24 }}>
        <Tabs
          defaultActiveKey="announcements"
          items={[
            {
              key: 'announcements',
              label: `当前公告 (${data.current_announcements.length})`,
              children: (
                <Table
                  rowKey="id"
                  columns={announcementColumns}
                  dataSource={data.current_announcements}
                  pagination={{ pageSize: 10, size: 'small' }}
                  size="small"
                  scroll={{ x: 1000 }}
                  locale={{
                    emptyText: <Empty description="暂无 BGP 公告" />,
                  }}
                />
              ),
            },
            {
              key: 'roa_vrp',
              label: `ROA/VRP 命中 (ROA: ${data.matched_roas.length}, VRP: ${data.matched_vrps.length})`,
              children: (
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  <div>
                    <Title level={5}>匹配的 ROA</Title>
                    <Table
                      rowKey="roa_id"
                      columns={roaColumns}
                      dataSource={data.matched_roas}
                      pagination={{ pageSize: 10, size: 'small' }}
                      size="small"
                      scroll={{ x: 1000 }}
                      locale={{
                        emptyText: <Empty description="无匹配 ROA" />,
                      }}
                    />
                  </div>
                  <div>
                    <Title level={5}>匹配的 VRP</Title>
                    <Table
                      rowKey="id"
                      columns={vrpColumns}
                      dataSource={data.matched_vrps}
                      pagination={{ pageSize: 10, size: 'small' }}
                      size="small"
                      scroll={{ x: 1000 }}
                      locale={{
                        emptyText: <Empty description="无匹配 VRP" />,
                      }}
                    />
                  </div>
                </Space>
              ),
            },
            {
              key: 'alerts',
              label: `告警历史 (${data.alerts.length})`,
              children: (
                <Table
                  rowKey="id"
                  columns={alertColumns}
                  dataSource={data.alerts}
                  pagination={{ pageSize: 10, size: 'small' }}
                  size="small"
                  scroll={{ x: 1200 }}
                  locale={{
                    emptyText: <Empty description="暂无告警记录" />,
                  }}
                />
              ),
            },
            {
              key: 'as_paths',
              label: `AS_PATH (${data.as_paths.length})`,
              children: data.as_paths.length ? (
                <List
                  bordered
                  dataSource={data.as_paths}
                  renderItem={(path, idx) => (
                    <List.Item>
                      <Space size={4} wrap>
                        <Text type="secondary">路径 {idx + 1}：</Text>
                        {path.map((asn, i) => (
                          <span key={i}>
                            <Tag color="blue">AS{asn}</Tag>
                            {i < path.length - 1 ? (
                              <span style={{ color: '#ccc', margin: '0 2px' }}>→</span>
                            ) : null}
                          </span>
                        ))}
                      </Space>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="暂无 AS_PATH 数据" />
              ),
            },
            {
              key: 'recommendations',
              label: `操作建议 (${recommendations.length})`,
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {recommendations.map((rec, idx) => {
                    const isHighRisk =
                      rec.includes('P0') ||
                      rec.includes('P1') ||
                      rec.includes('Invalid') ||
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
              ),
            },
          ]}
        />
      </Card>
    </PageContainer>
  );
}

export default PrefixDetail;
