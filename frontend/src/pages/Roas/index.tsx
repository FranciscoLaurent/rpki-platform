// ROA 管理页面
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  Card,
  Col,
  Empty,
  Progress,
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
  checkROAConflicts,
  checkROAMissing,
  getROACoverage,
  getROAs,
} from '@/api/roas';
import type {
  ROA,
  ROAConflictResult,
  ROAMissingResult,
} from '@/api/roas';

const { Text } = Typography;

/** ROA 状态颜色映射 */
const ROA_STATUS_COLOR: Record<string, string> = {
  valid: 'green',
  expired: 'red',
  revoked: 'default',
};

/** ROA 状态标签映射 */
const ROA_STATUS_LABEL: Record<string, string> = {
  valid: '有效',
  expired: '已过期',
  revoked: '已撤销',
};

/** 默认分页参数 */
const DEFAULT_PAGE_SIZE = 10;

/** ROA 管理页面 */
function Roas() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  /** 拉取 ROA 列表 */
  const {
    data: roasData,
    isLoading: roasLoading,
    isFetching: roasFetching,
    refetch: refetchRoas,
  } = useQuery({
    queryKey: ['roas', page, pageSize],
    queryFn: () => getROAs({ page, page_size: pageSize }),
  });

  /** 拉取 ROA 覆盖率统计 */
  const { data: coverage, isLoading: coverageLoading } = useQuery({
    queryKey: ['roas-coverage'],
    queryFn: getROACoverage,
  });

  /** 拉取 ROA 缺失检测结果 */
  const { data: missingList, isLoading: missingLoading } = useQuery({
    queryKey: ['roas-missing'],
    queryFn: checkROAMissing,
  });

  /** 拉取 ROA 冲突检测结果 */
  const { data: conflictList, isLoading: conflictLoading } = useQuery({
    queryKey: ['roas-conflicts'],
    queryFn: checkROAConflicts,
  });

  /** 缺失 ROA 前缀列表（过滤出无 ROA 的项） */
  const missingPrefixes = (missingList ?? []).filter(
    (item: ROAMissingResult) => !item.has_roa,
  );

  /** 表格列定义：ROA 列表 */
  const roaColumns: ColumnsType<ROA> = [
    {
      title: '前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '起源 AS',
      dataIndex: 'origin_as',
      key: 'origin_as',
      width: 120,
      render: (v: number) => <Tag color="blue">AS{v}</Tag>,
    },
    {
      title: 'maxLength',
      dataIndex: 'max_length',
      key: 'max_length',
      width: 120,
      align: 'center' as const,
      render: (v: number | null) => (v ?? '-') as React.ReactNode,
    },
    {
      title: 'TAL ID',
      dataIndex: 'tal_id',
      key: 'tal_id',
      width: 100,
      align: 'center' as const,
      render: (v: number | null) => (v ?? '-') as React.ReactNode,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      align: 'center' as const,
      render: (v: string) => (
        <Tag color={ROA_STATUS_COLOR[v] ?? 'default'}>
          {ROA_STATUS_LABEL[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '有效期',
      key: 'validity',
      width: 220,
      render: (_: unknown, record: ROA) => {
        if (!record.not_after) return '-';
        const expired = dayjs(record.not_after).isBefore(dayjs());
        return (
          <Space direction="vertical" size={0}>
            <Text type={expired ? 'danger' : undefined}>
              {dayjs(record.not_after).format('YYYY-MM-DD HH:mm:ss')}
            </Text>
            {record.not_before ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                起 {dayjs(record.not_before).format('YYYY-MM-DD')}
              </Text>
            ) : null}
          </Space>
        );
      },
    },
  ];

  /** 表格分页配置 */
  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total: roasData?.total ?? 0,
    showSizeChanger: true,
    showTotal: (total) => `共 ${total} 条`,
    onChange: (p, ps) => {
      setPage(p);
      setPageSize(ps);
    },
  };

  /** 覆盖率百分比（0-100） */
  const coveragePercent = Math.round(
    (coverage?.coverage_rate ?? 0) * 100,
  );

  /** 渲染加载中 */
  if (coverageLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="加载 ROA 数据..." />
      </div>
    );
  }

  return (
    <PageContainer
      title="ROA 管理"
      subtitle="管理 ROA 生命周期，监控覆盖率、缺失与冲突"
      extra={
        <Button
          loading={roasFetching}
          onClick={() => refetchRoas()}
        >
          刷新
        </Button>
      }
    >
      {/* 顶部覆盖率统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="总前缀数"
              value={coverage?.total_prefixes ?? 0}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="已覆盖前缀数"
              value={coverage?.covered_prefixes ?? 0}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="覆盖率"
              value={coveragePercent}
              suffix="%"
              precision={0}
              valueStyle={{ color: coveragePercent >= 80 ? '#52c41a' : '#faad14' }}
            />
            <Progress
              percent={coveragePercent}
              size="small"
              status={
                coveragePercent >= 80
                  ? 'success'
                  : coveragePercent >= 50
                  ? 'normal'
                  : 'exception'
              }
              style={{ marginTop: 8, marginBottom: 0 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable bodyStyle={{ padding: 24 }}>
            <Statistic
              title="缺失 ROA 数量"
              value={missingPrefixes.length}
              valueStyle={{
                color: missingPrefixes.length > 0 ? '#cf1322' : '#52c41a',
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* ROA 列表表格 */}
      <Card
        title="ROA 列表"
        bodyStyle={{ padding: 0 }}
        style={{ marginTop: 16 }}
      >
        <Table<ROA>
          rowKey="id"
          columns={roaColumns}
          dataSource={roasData?.items ?? []}
          loading={roasLoading}
          pagination={pagination}
          size="small"
          locale={{ emptyText: <Empty description="暂无 ROA 数据" /> }}
        />
      </Card>

      {/* 缺失检测结果 */}
      <Card
        title="缺失检测结果"
        bodyStyle={{ padding: 16 }}
        style={{ marginTop: 16 }}
      >
        {missingLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : missingPrefixes.length === 0 ? (
          <Empty description="所有前缀均已覆盖 ROA" />
        ) : (
          <Space wrap>
            {missingPrefixes.map((item: ROAMissingResult) => (
              <Tag key={`${item.prefix}-${item.origin_as}`} color="red">
                {item.prefix} (AS{item.origin_as})
              </Tag>
            ))}
          </Space>
        )}
      </Card>

      {/* 冲突检测结果 */}
      <Card
        title="冲突检测结果"
        bodyStyle={{ padding: 16 }}
        style={{ marginTop: 16 }}
      >
        {conflictLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : !conflictList || conflictList.length === 0 ? (
          <Empty description="无 ROA 冲突" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            {conflictList.map((item: ROAConflictResult, idx: number) => (
              <Card
                key={`${item.prefix}-${idx}`}
                size="small"
                bodyStyle={{ padding: 12 }}
                style={{ background: '#fafafa' }}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space>
                    <Text code>{item.prefix}</Text>
                    {item.origin_as ? (
                      <Tag color="blue">AS{item.origin_as}</Tag>
                    ) : null}
                    <Tag color="volcano">{item.conflict_type}</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {item.description}
                  </Text>
                  {item.conflicting_roas.length > 0 ? (
                    <Space wrap>
                      {item.conflicting_roas.map((roa: ROA) => (
                        <Tag key={roa.id} color="orange">
                          {roa.prefix} / AS{roa.origin_as}
                          {roa.max_length ? ` / max ${roa.max_length}` : ''}
                        </Tag>
                      ))}
                    </Space>
                  ) : null}
                </Space>
              </Card>
            ))}
          </Space>
        )}
      </Card>
    </PageContainer>
  );
}

export default Roas;
