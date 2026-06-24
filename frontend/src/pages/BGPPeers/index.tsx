// BGP 邻居管理页面
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Dropdown,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import PageContainer from '@/components/PageContainer';
import SearchBar from '@/components/SearchBar';
import { deleteBGPPeer, getBGPPeers } from '@/api/bgp-peers';
import type { BGPPeer, BGPPeerQueryParams } from '@/api/bgp-peers';
import BGPPeerForm from './BGPPeerForm';

const { Text } = Typography;

/** 会话状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  established: 'green',
  active: 'blue',
  connect: 'gold',
  idle: 'default',
  down: 'red',
};

/** 会话类型颜色映射 */
const SESSION_TYPE_COLOR: Record<string, string> = {
  ebgp: 'blue',
  ibgp: 'green',
  'rr-client': 'cyan',
  'rs-client': 'purple',
};

/** 状态选项 */
const STATUS_OPTIONS = [
  { value: 'established', label: 'Established' },
  { value: 'active', label: 'Active' },
  { value: 'connect', label: 'Connect' },
  { value: 'idle', label: 'Idle' },
  { value: 'down', label: 'Down' },
];

/** 会话类型选项 */
const SESSION_TYPE_OPTIONS = [
  { value: 'ebgp', label: 'eBGP' },
  { value: 'ibgp', label: 'iBGP' },
  { value: 'rr-client', label: 'RR Client' },
  { value: 'rs-client', label: 'RS Client' },
];

/** 地址族选项 */
const FAMILY_OPTIONS = [
  { value: 4, label: 'IPv4' },
  { value: 6, label: 'IPv6' },
];

/** BGP 邻居管理主页面 */
function BGPPeers() {
  const queryClient = useQueryClient();
  const [queryParams, setQueryParams] = useState<BGPPeerQueryParams>({
    page: 1,
    page_size: 10,
  });
  const [searchText, setSearchText] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingPeer, setEditingPeer] = useState<BGPPeer | null>(null);

  /** 列表查询 */
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['bgp-peers', queryParams],
    queryFn: () => getBGPPeers(queryParams),
    placeholderData: (prev) => prev,
  });

  /** 删除 mutation */
  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteBGPPeer(id),
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['bgp-peers'] });
    },
  });

  /** 处理搜索 */
  const handleSearch = (value: string) => {
    setQueryParams((prev) => ({ ...prev, page: 1, search: value || undefined }));
  };

  /** 处理过滤变化 */
  const handleFilterChange = (key: keyof BGPPeerQueryParams, value: unknown) => {
    setQueryParams((prev) => ({
      ...prev,
      page: 1,
      [key]: value ?? undefined,
    }));
  };

  /** 处理分页变化 */
  const handleTableChange = (pagination: TablePaginationConfig) => {
    setQueryParams((prev) => ({
      ...prev,
      page: pagination.current,
      page_size: pagination.pageSize,
    }));
  };

  /** 新建 BGP 邻居 */
  const handleCreate = () => {
    setEditingPeer(null);
    setFormOpen(true);
  };

  /** 编辑 BGP 邻居 */
  const handleEdit = (record: BGPPeer) => {
    setEditingPeer(record);
    setFormOpen(true);
  };

  /** 删除 BGP 邻居 */
  const handleDelete = (record: BGPPeer) => {
    deleteMutation.mutate(record.id);
  };

  /** 行操作菜单 */
  const rowMenuItems = (record: BGPPeer): MenuProps['items'] => [
    {
      key: 'edit',
      icon: <EditOutlined />,
      label: '编辑',
      onClick: () => handleEdit(record),
    },
    { type: 'divider' },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      label: '删除',
      danger: true,
      onClick: () =>
        Modal.confirm({
          title: '确认删除',
          content: `确定要删除 BGP 邻居 ${record.peer_ip} (AS${record.remote_asn}) 吗？`,
          okType: 'danger',
          okText: '删除',
          cancelText: '取消',
          onOk: () => handleDelete(record),
        }),
    },
  ];

  /** 表格列定义 */
  const columns: ColumnsType<BGPPeer> = useMemo(
    () => [
      {
        title: 'Peer IP',
        dataIndex: 'peer_ip',
        key: 'peer_ip',
        width: 180,
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: 'Remote ASN',
        dataIndex: 'remote_asn',
        key: 'remote_asn',
        width: 130,
        render: (v: number) => `AS${v}`,
      },
      {
        title: '地址族',
        dataIndex: 'address_family',
        key: 'address_family',
        width: 100,
        render: (v: number) => <Tag>IPv{v}</Tag>,
      },
      {
        title: '会话类型',
        dataIndex: 'session_type',
        key: 'session_type',
        width: 130,
        render: (v: string) => (
          <Tag color={SESSION_TYPE_COLOR[v] || 'default'}>{v}</Tag>
        ),
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 130,
        render: (v: string) => (
          <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>
        ),
      },
      {
        title: '最大前缀数',
        dataIndex: 'max_prefixes',
        key: 'max_prefixes',
        width: 120,
        render: (v: number) => v.toLocaleString(),
      },
      {
        title: '路由策略',
        dataIndex: 'route_policy',
        key: 'route_policy',
        width: 200,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: '描述',
        dataIndex: 'description',
        key: 'description',
        width: 200,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: '操作',
        key: 'action',
        width: 120,
        fixed: 'right',
        render: (_, record) => (
          <Space size={4}>
            <Tooltip title="编辑">
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => handleEdit(record)}
              />
            </Tooltip>
            <Dropdown menu={{ items: rowMenuItems(record) }} trigger={['click']}>
              <Button type="text" size="small">
                更多
              </Button>
            </Dropdown>
          </Space>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  return (
    <PageContainer
      title="BGP 邻居管理"
      subtitle="管理 BGP 会话邻居及路由策略配置"
      extra={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching} />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建 BGP 邻居
          </Button>
        </Space>
      }
    >
      <SearchBar
        placeholder="搜索 Peer IP、路由策略、描述..."
        value={searchText}
        onChange={setSearchText}
        onSearch={handleSearch}
        searchWidth={300}
        filters={[
          {
            key: 'family',
            node: (
              <Select
                allowClear
                placeholder="地址族"
                style={{ width: 120 }}
                options={FAMILY_OPTIONS}
                value={queryParams.address_family}
                onChange={(v) => handleFilterChange('address_family', v)}
              />
            ),
          },
          {
            key: 'session_type',
            node: (
              <Select
                allowClear
                placeholder="会话类型"
                style={{ width: 140 }}
                options={SESSION_TYPE_OPTIONS}
                value={queryParams.session_type}
                onChange={(v) => handleFilterChange('session_type', v)}
              />
            ),
          },
          {
            key: 'status',
            node: (
              <Select
                allowClear
                placeholder="状态"
                style={{ width: 140 }}
                options={STATUS_OPTIONS}
                value={queryParams.status}
                onChange={(v) => handleFilterChange('status', v)}
              />
            ),
          },
        ]}
      />

      <Table<BGPPeer>
        rowKey="id"
        columns={columns}
        dataSource={data?.items}
        loading={isLoading}
        onChange={handleTableChange}
        scroll={{ x: 1200 }}
        pagination={{
          current: data?.page || queryParams.page,
          pageSize: data?.page_size || queryParams.page_size,
          total: data?.total || 0,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        expandable={{
          expandedRowRender: (record) => (
            <Space split={<span style={{ color: '#ccc' }}>|</span>} wrap>
              <span>
                <Text type="secondary">创建时间：</Text>
                {record.created_at}
              </span>
              <span>
                <Text type="secondary">更新时间：</Text>
                {record.updated_at}
              </span>
            </Space>
          ),
        }}
      />

      <BGPPeerForm
        open={formOpen}
        peer={editingPeer}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['bgp-peers'] });
        }}
      />
    </PageContainer>
  );
}

export default BGPPeers;
