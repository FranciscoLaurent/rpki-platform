// IP 前缀管理页面
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Card,
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
  ApartmentOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import PageContainer from '@/components/PageContainer';
import SearchBar from '@/components/SearchBar';
import { deletePrefix, getPrefixes } from '@/api/prefixes';
import type { Prefix, PrefixQueryParams } from '@/api/prefixes';
import PrefixForm from './PrefixForm';
import PrefixTree from './PrefixTree';
import BatchImport from './BatchImport';
import RelationshipView from './RelationshipView';

const { Text } = Typography;

/** 状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  reserved: 'blue',
  deprecated: 'default',
  conflict: 'red',
};

/** 重要性颜色映射 */
const IMPORTANCE_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'default',
};

/** 状态选项 */
const STATUS_OPTIONS = [
  { value: 'active', label: '活跃' },
  { value: 'reserved', label: '保留' },
  { value: 'deprecated', label: '废弃' },
  { value: 'conflict', label: '冲突' },
];

/** 重要性选项 */
const IMPORTANCE_OPTIONS = [
  { value: 'critical', label: '关键' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
];

/** 地址族选项 */
const FAMILY_OPTIONS = [
  { value: 4, label: 'IPv4' },
  { value: 6, label: 'IPv6' },
];

/** IP 前缀管理主页面 */
function Prefixes() {
  const queryClient = useQueryClient();
  const [queryParams, setQueryParams] = useState<PrefixQueryParams>({
    page: 1,
    page_size: 10,
  });
  const [searchText, setSearchText] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingPrefix, setEditingPrefix] = useState<Prefix | null>(null);
  const [treeOpen, setTreeOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [selectedPrefixId, setSelectedPrefixId] = useState<number | null>(null);

  /** 列表查询 */
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['prefixes', queryParams],
    queryFn: () => getPrefixes(queryParams),
    placeholderData: (prev) => prev,
  });

  /** 删除 mutation */
  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePrefix(id),
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['prefixes'] });
      queryClient.invalidateQueries({ queryKey: ['prefix-tree'] });
    },
  });

  /** 处理搜索 */
  const handleSearch = (value: string) => {
    setQueryParams((prev) => ({ ...prev, page: 1, search: value || undefined }));
  };

  /** 处理过滤变化 */
  const handleFilterChange = (key: keyof PrefixQueryParams, value: unknown) => {
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

  /** 新建前缀 */
  const handleCreate = () => {
    setEditingPrefix(null);
    setFormOpen(true);
  };

  /** 编辑前缀 */
  const handleEdit = (record: Prefix) => {
    setEditingPrefix(record);
    setFormOpen(true);
  };

  /** 查看关系 */
  const handleViewRelationship = (record: Prefix) => {
    setSelectedPrefixId(record.id);
  };

  /** 删除前缀 */
  const handleDelete = (record: Prefix) => {
    deleteMutation.mutate(record.id);
  };

  /** 行操作菜单 */
  const rowMenuItems = (record: Prefix): MenuProps['items'] => [
    {
      key: 'view',
      icon: <EyeOutlined />,
      label: '查看关系',
      onClick: () => handleViewRelationship(record),
    },
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
          content: `确定要删除前缀 ${record.prefix} 吗？`,
          okType: 'danger',
          okText: '删除',
          cancelText: '取消',
          onOk: () => handleDelete(record),
        }),
    },
  ];

  /** 表格列定义 */
  const columns: ColumnsType<Prefix> = useMemo(
    () => [
      {
        title: '前缀',
        dataIndex: 'prefix',
        key: 'prefix',
        render: (text: string) => <Text strong>{text}</Text>,
      },
      {
        title: '地址族',
        dataIndex: 'prefix_family',
        key: 'prefix_family',
        width: 90,
        render: (v: number) => <Tag>IPv{v}</Tag>,
        filters: [
          { text: 'IPv4', value: 4 },
          { text: 'IPv6', value: 6 },
        ],
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
        render: (v: string) => (
          <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>
        ),
      },
      {
        title: '重要性',
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
        width: 160,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: '地域',
        dataIndex: 'region',
        key: 'region',
        width: 120,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: '标签',
        dataIndex: 'tags',
        key: 'tags',
        width: 160,
        render: (tags: string[]) =>
          tags?.length ? (
            <Space size={4} wrap>
              {tags.slice(0, 3).map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
              {tags.length > 3 && <Tag>+{tags.length - 3}</Tag>}
            </Space>
          ) : (
            '-'
          ),
      },
      {
        title: '操作',
        key: 'action',
        width: 120,
        fixed: 'right',
        render: (_, record) => (
          <Space size={4}>
            <Tooltip title="查看关系">
              <Button
                type="text"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => handleViewRelationship(record)}
              />
            </Tooltip>
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
      title="IP 前缀管理"
      subtitle="管理 IPv4/IPv6 前缀资源，支持层级关系与批量导入"
      extra={
        <Space wrap>
          <Button
            icon={<ApartmentOutlined />}
            onClick={() => setTreeOpen((v) => !v)}
            type={treeOpen ? 'primary' : 'default'}
          >
            {treeOpen ? '隐藏前缀树' : '查看前缀树'}
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => setBatchOpen(true)}>
            批量导入
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching} />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建前缀
          </Button>
        </Space>
      }
    >
      <SearchBar
        placeholder="搜索前缀、业务归属、描述..."
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
                value={queryParams.prefix_family}
                onChange={(v) => handleFilterChange('prefix_family', v)}
              />
            ),
          },
          {
            key: 'status',
            node: (
              <Select
                allowClear
                placeholder="状态"
                style={{ width: 120 }}
                options={STATUS_OPTIONS}
                value={queryParams.status}
                onChange={(v) => handleFilterChange('status', v)}
              />
            ),
          },
          {
            key: 'importance',
            node: (
              <Select
                allowClear
                placeholder="重要性"
                style={{ width: 120 }}
                options={IMPORTANCE_OPTIONS}
                value={queryParams.importance}
                onChange={(v) => handleFilterChange('importance', v)}
              />
            ),
          },
        ]}
      />

      {treeOpen && (
        <div style={{ marginBottom: 16 }}>
          <PrefixTree open={treeOpen} />
        </div>
      )}

      <Table<Prefix>
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
            <Card size="small" bordered={false} style={{ background: '#fafafa' }}>
              <Typography.Paragraph style={{ margin: 0 }}>
                <Space split={<span style={{ color: '#ccc' }}>|</span>} wrap>
                  <span>
                    <Text type="secondary">机房：</Text>
                    {record.site || '-'}
                  </span>
                  <span>
                    <Text type="secondary">云区域：</Text>
                    {record.cloud_zone || '-'}
                  </span>
                  <span>
                    <Text type="secondary">客户ID：</Text>
                    {record.customer_id ?? '-'}
                  </span>
                  <span>
                    <Text type="secondary">父前缀ID：</Text>
                    {record.parent_id ?? '-'}
                  </span>
                  <span>
                    <Text type="secondary">创建时间：</Text>
                    {record.created_at}
                  </span>
                </Space>
              </Typography.Paragraph>
              {record.description && (
                <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
                  {record.description}
                </Typography.Paragraph>
              )}
            </Card>
          ),
        }}
      />

      {/* 关系视图区域 */}
      {selectedPrefixId !== null && (
        <div style={{ marginTop: 16 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 8,
            }}
          >
            <Typography.Title level={5} style={{ margin: 0 }}>
              关系视图
            </Typography.Title>
            <Button size="small" onClick={() => setSelectedPrefixId(null)}>
              关闭
            </Button>
          </div>
          <RelationshipView prefixId={selectedPrefixId} />
        </div>
      )}

      {/* 新建/编辑表单 */}
      <PrefixForm
        open={formOpen}
        prefix={editingPrefix}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['prefixes'] });
          queryClient.invalidateQueries({ queryKey: ['prefix-tree'] });
        }}
      />

      {/* 批量导入 */}
      <BatchImport
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['prefixes'] });
          queryClient.invalidateQueries({ queryKey: ['prefix-tree'] });
        }}
      />
    </PageContainer>
  );
}

export default Prefixes;
