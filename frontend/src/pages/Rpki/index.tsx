// RPKI 管理页面
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
  message,
} from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import {
  DatabaseOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { getRPKIHealth, getTALs, getVRPs, triggerSync } from '@/api/rpki';
import type { TAL, VRP } from '@/api/rpki';

const { Text } = Typography;

/** TAL 状态颜色映射 */
const TAL_STATUS_COLOR: Record<string, string> = {
  active: 'green',
  inactive: 'default',
};

/** TAL 同步状态颜色映射 */
const SYNC_STATUS_COLOR: Record<string, string> = {
  success: 'green',
  pending: 'orange',
  failed: 'red',
};

/** VRP 验证状态颜色映射 */
const VALIDATION_STATUS_COLOR: Record<string, string> = {
  valid: 'green',
  invalid: 'red',
  not_found: 'orange',
};

/** 整体同步状态颜色映射 */
const OVERALL_STATUS_COLOR: Record<string, string> = {
  healthy: 'green',
  stale: 'orange',
  unknown: 'default',
};

/** 整体同步状态标签映射 */
const OVERALL_STATUS_LABEL: Record<string, string> = {
  healthy: '健康',
  stale: '过期',
  unknown: '未知',
};

/** RPKI 管理页面 */
function Rpki() {
  const queryClient = useQueryClient();
  const [vrpPagination, setVrpPagination] = useState({
    page: 1,
    pageSize: 10,
  });

  /** 拉取 TAL 列表 */
  const {
    data: talsData,
    isLoading: talsLoading,
    isFetching: talsFetching,
    refetch: refetchTals,
  } = useQuery({
    queryKey: ['rpki-tals'],
    queryFn: () => getTALs({ skip: 0, limit: 100 }),
  });

  /** 拉取 VRP 列表（分页） */
  const {
    data: vrpsData,
    isLoading: vrpsLoading,
    isFetching: vrpsFetching,
    refetch: refetchVrps,
  } = useQuery({
    queryKey: ['rpki-vrps', vrpPagination],
    queryFn: () =>
      getVRPs({
        skip: (vrpPagination.page - 1) * vrpPagination.pageSize,
        limit: vrpPagination.pageSize,
      }),
  });

  /** 拉取 RPKI 健康状态 */
  const {
    data: healthData,
    isLoading: healthLoading,
    isFetching: healthFetching,
    refetch: refetchHealth,
  } = useQuery({
    queryKey: ['rpki-health'],
    queryFn: getRPKIHealth,
  });

  /** 触发同步 mutation */
  const syncMutation = useMutation({
    mutationFn: triggerSync,
    onSuccess: (data) => {
      message.success(data.message || '同步已触发');
      queryClient.invalidateQueries({ queryKey: ['rpki-tals'] });
      queryClient.invalidateQueries({ queryKey: ['rpki-vrps'] });
      queryClient.invalidateQueries({ queryKey: ['rpki-health'] });
    },
  });

  /** 刷新所有数据 */
  const handleRefresh = () => {
    refetchTals();
    refetchVrps();
    refetchHealth();
  };

  /** VRP 分页变化 */
  const handleVrpTableChange = (pagination: TablePaginationConfig) => {
    setVrpPagination({
      page: pagination.current ?? 1,
      pageSize: pagination.pageSize ?? 10,
    });
  };

  /** 计算最后同步时间（取所有 TAL 中最新的） */
  const lastSyncedAt = (() => {
    if (!talsData?.items?.length) return null;
    const times = talsData.items
      .map((t) => t.last_synced_at)
      .filter((t): t is string => !!t)
      .map((t) => dayjs(t));
    if (!times.length) return null;
    return times.sort((a, b) => b.valueOf() - a.valueOf())[0];
  })();

  /** 计算整体同步状态 */
  const overallStatus = (() => {
    if (!healthData) return 'unknown';
    if (healthData.overall_healthy) return 'healthy';
    if (healthData.failed_repositories > 0) return 'stale';
    return 'unknown';
  })();

  /** TAL 表格列定义 */
  const talColumns: ColumnsType<TAL> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'URI',
      dataIndex: 'uri',
      key: 'uri',
      ellipsis: true,
      render: (v: string) => (
        <Text copyable style={{ fontSize: 12 }}>
          {v}
        </Text>
      ),
    },
    {
      title: 'rsync URI',
      dataIndex: 'rsync_uri',
      key: 'rsync_uri',
      ellipsis: true,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '-'}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => (
        <Tag color={TAL_STATUS_COLOR[v] || 'default'}>{v}</Tag>
      ),
    },
    {
      title: '同步状态',
      dataIndex: 'sync_status',
      key: 'sync_status',
      width: 110,
      render: (v: string) => (
        <Tag color={SYNC_STATUS_COLOR[v] || 'default'}>{v}</Tag>
      ),
    },
    {
      title: '最后同步时间',
      dataIndex: 'last_synced_at',
      key: 'last_synced_at',
      width: 180,
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
  ];

  /** VRP 表格列定义 */
  const vrpColumns: ColumnsType<VRP> = [
    {
      title: '前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      width: 220,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '起源 AS',
      dataIndex: 'origin_as',
      key: 'origin_as',
      width: 120,
      render: (v: number) => `AS${v}`,
    },
    {
      title: 'maxLength',
      dataIndex: 'max_length',
      key: 'max_length',
      width: 120,
      render: (v: number | null) => v ?? '-',
    },
    {
      title: 'TAL',
      dataIndex: 'trust_anchor',
      key: 'trust_anchor',
      width: 160,
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '验证状态',
      dataIndex: 'validation_status',
      key: 'validation_status',
      width: 120,
      render: (v: string) => (
        <Tag color={VALIDATION_STATUS_COLOR[v] || 'default'}>{v}</Tag>
      ),
    },
  ];

  /** 初始加载中 */
  if (talsLoading && vrpsLoading && healthLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="加载 RPKI 数据..." />
      </div>
    );
  }

  const isRefreshing = talsFetching || vrpsFetching || healthFetching;

  return (
    <PageContainer
      title="RPKI 管理"
      subtitle="管理信任锚定位器（TAL）与可验证路由声明（VRP）"
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={isRefreshing}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<SyncOutlined />}
            onClick={() => syncMutation.mutate()}
            loading={syncMutation.isPending}
          >
            触发同步
          </Button>
        </Space>
      }
    >
      {/* 顶部统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 24 } }}>
            <Statistic
              title="TAL 总数"
              value={talsData?.total ?? 0}
              prefix={<DatabaseOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 24 } }}>
            <Statistic
              title="VRP 总数"
              value={vrpsData?.total ?? 0}
              prefix={
                <SafetyCertificateOutlined style={{ color: '#52c41a' }} />
              }
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 24 } }}>
            <div style={{ marginBottom: 4 }}>
              <Text type="secondary">同步状态</Text>
            </div>
            <Tag
              color={OVERALL_STATUS_COLOR[overallStatus]}
              style={{ fontSize: 16, padding: '4px 16px' }}
            >
              {OVERALL_STATUS_LABEL[overallStatus]}
            </Tag>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                健康 {healthData?.healthy_repositories ?? 0} · 失败{' '}
                {healthData?.failed_repositories ?? 0} · 总数{' '}
                {healthData?.total_repositories ?? 0}
              </Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card styles={{ body: { padding: 24 } }}>
            <Statistic
              title="最后同步时间"
              value={
                lastSyncedAt
                  ? dayjs(lastSyncedAt).format('YYYY-MM-DD HH:mm:ss')
                  : '尚未同步'
              }
            />
          </Card>
        </Col>
      </Row>

      {/* TAL 列表表格 */}
      <Card
        title="TAL 列表"
        styles={{ body: { padding: 0 } }}
        style={{ marginTop: 16 }}
      >
        <Table<TAL>
          rowKey="id"
          columns={talColumns}
          dataSource={talsData?.items}
          loading={talsLoading}
          pagination={false}
          size="small"
          scroll={{ x: 1000 }}
          locale={{ emptyText: <Empty description="暂无 TAL 数据" /> }}
        />
      </Card>

      {/* VRP 列表表格 */}
      <Card
        title="VRP 列表"
        styles={{ body: { padding: 0 } }}
        style={{ marginTop: 16 }}
      >
        <Table<VRP>
          rowKey="id"
          columns={vrpColumns}
          dataSource={vrpsData?.items}
          loading={vrpsLoading}
          onChange={handleVrpTableChange}
          scroll={{ x: 800 }}
          locale={{ emptyText: <Empty description="暂无 VRP 数据" /> }}
          pagination={{
            current: vrpPagination.page,
            pageSize: vrpPagination.pageSize,
            total: vrpsData?.total ?? 0,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>
    </PageContainer>
  );
}

export default Rpki;
