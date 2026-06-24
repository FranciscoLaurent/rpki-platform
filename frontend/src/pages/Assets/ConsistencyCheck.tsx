// 资产一致性检查页面
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { consistencyCheck } from '@/api/assets';
import type { ConsistencyIssue } from '@/api/assets';

const { Text } = Typography;

/** 严重程度颜色映射 */
const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'blue',
  info: 'default',
};

/** 严重程度选项 */
const SEVERITY_OPTIONS = [
  { value: 'critical', label: '严重' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
  { value: 'info', label: '提示' },
];

/** 资产一致性检查页面 */
function ConsistencyCheck() {
  const [enabled, setEnabled] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<string | undefined>(undefined);

  /** 触发检查查询 */
  const { data, isLoading, isFetching, refetch, error } = useQuery({
    queryKey: ['consistency-check'],
    queryFn: consistencyCheck,
    enabled,
  });

  /** 执行检查 */
  const handleRunCheck = () => {
    setEnabled(true);
    void refetch();
  };

  /** 按严重程度过滤的问题列表 */
  const filteredIssues = useMemo(() => {
    if (!data?.issues) return [];
    if (!severityFilter) return data.issues;
    return data.issues.filter((i) => i.severity === severityFilter);
  }, [data, severityFilter]);

  /** 表格列定义 */
  const columns: ColumnsType<ConsistencyIssue> = useMemo(
    () => [
      {
        title: '类型',
        dataIndex: 'type',
        key: 'type',
        width: 180,
        render: (v: string) => <Tag>{v}</Tag>,
      },
      {
        title: '前缀',
        dataIndex: 'prefix',
        key: 'prefix',
        width: 200,
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: '描述',
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
      },
      {
        title: '严重程度',
        dataIndex: 'severity',
        key: 'severity',
        width: 110,
        render: (v: string) => (
          <Tag color={SEVERITY_COLOR[v] || 'default'}>{v}</Tag>
        ),
      },
      {
        title: '检测时间',
        dataIndex: 'detected_at',
        key: 'detected_at',
        width: 180,
        render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: '修复建议',
        dataIndex: 'recommendation',
        key: 'recommendation',
        width: 280,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
    ],
    [],
  );

  return (
    <PageContainer
      title="资产一致性检查"
      subtitle="检查前缀、ASN、ROA、BGP 之间的数据一致性"
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            loading={isFetching}
            disabled={!enabled}
          >
            重新检查
          </Button>
          <Button
            type="primary"
            icon={<ExclamationCircleOutlined />}
            onClick={handleRunCheck}
            loading={isLoading}
          >
            执行检查
          </Button>
        </Space>
      }
    >
      {!enabled && !data && (
        <Empty
          description="点击右上角「执行检查」按钮开始一致性检查"
          style={{ padding: 48 }}
        />
      )}

      {error && (
        <Alert
          style={{ marginBottom: 16 }}
          type="error"
          message="检查失败"
          description={(error as Error).message}
        />
      )}

      {data && (
        <>
          {/* 概览统计 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}>
              <Card>
                <Statistic
                  title="问题总数"
                  value={data.total_issues}
                  prefix={<ExclamationCircleOutlined />}
                  valueStyle={{ color: '#1677ff' }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card>
                <Statistic
                  title="严重 (Critical)"
                  value={data.by_severity?.critical || 0}
                  prefix={<WarningOutlined />}
                  valueStyle={{ color: '#cf1322' }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card>
                <Statistic
                  title="高 (High)"
                  value={data.by_severity?.high || 0}
                  valueStyle={{ color: '#fa8c16' }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card>
                <Statistic
                  title="检查时间"
                  value={data.checked_at ? dayjs(data.checked_at).format('MM-DD HH:mm:ss') : '-'}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
          </Row>

          {/* 过滤栏 */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 16,
            }}
          >
            <Text type="secondary">
              共 {data.total_issues} 个问题，当前显示 {filteredIssues.length} 个
            </Text>
            <Space>
              <Text type="secondary">按严重程度过滤：</Text>
              <Select
                allowClear
                placeholder="全部"
                style={{ width: 140 }}
                options={SEVERITY_OPTIONS}
                value={severityFilter}
                onChange={setSeverityFilter}
              />
            </Space>
          </div>

          {/* 问题列表 */}
          <Table<ConsistencyIssue>
            rowKey="id"
            columns={columns}
            dataSource={filteredIssues}
            loading={isLoading}
            scroll={{ x: 1000 }}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
            }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <Space direction="vertical" align="center">
                      <CheckCircleOutlined style={{ fontSize: 32, color: '#52c41a' }} />
                      <Text type="secondary">
                        {data.total_issues === 0
                          ? '所有资产数据一致，未发现问题'
                          : '当前过滤条件下无问题'}
                      </Text>
                    </Space>
                  }
                />
              ),
            }}
          />
        </>
      )}
    </PageContainer>
  );
}

export default ConsistencyCheck;
