// ASN 管理页面
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
import { deleteASN, getASNs } from '@/api/asns';
import type { ASN, ASNQueryParams } from '@/api/asns';
import ASNForm from './ASNForm';

const { Text } = Typography;

/** 状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  suspended: 'orange',
  deprecated: 'default',
};

/** 类型颜色映射 */
const TYPE_COLOR: Record<string, string> = {
  transit: 'blue',
  customer: 'green',
  peer: 'cyan',
  internal: 'default',
};

/** 风险画像颜色映射 */
const RISK_COLOR: Record<string, string> = {
  low: 'green',
  medium: 'gold',
  high: 'orange',
  critical: 'red',
};

/** 状态选项 */
const STATUS_OPTIONS = [
  { value: 'active', label: '活跃' },
  { value: 'suspended', label: '暂停' },
  { value: 'deprecated', label: '废弃' },
];

/** 类型选项 */
const TYPE_OPTIONS = [
  { value: 'transit', label: 'transit' },
  { value: 'customer', label: 'customer' },
  { value: 'peer', label: 'peer' },
  { value: 'internal', label: 'internal' },
];

/** 风险画像选项 */
const RISK_OPTIONS = [
  { value: 'low', label: '低风险' },
  { value: 'medium', label: '中风险' },
  { value: 'high', label: '高风险' },
  { value: 'critical', label: '极高风险' },
];

/** ASN 管理主页面 */
function ASNs() {
  const queryClient = useQueryClient();
  const [queryParams, setQueryParams] = useState<ASNQueryParams>({
    page: 1,
    page_size: 10,
  });
  const [searchText, setSearchText] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingASN, setEditingASN] = useState<ASN | null>(null);

  /** 列表查询 */
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['asns', queryParams],
    queryFn: () => getASNs(queryParams),
    placeholderData: (prev) => prev,
  });

  /** 删除 mutation */
  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteASN(id),
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['asns'] });
    },
  });

  /** 处理搜索 */
  const handleSearch = (value: string) => {
    setQueryParams((prev) => ({ ...prev, page: 1, search: value || undefined }));
  };

  /** 处理过滤变化 */
  const handleFilterChange = (key: keyof ASNQueryParams, value: unknown) => {
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

  /** 新建 ASN */
  const handleCreate = () => {
    setEditingASN(null);
    setFormOpen(true);
  };

  /** 编辑 ASN */
  const handleEdit = (record: ASN) => {
    setEditingASN(record);
    setFormOpen(true);
  };

  /** 删除 ASN */
  const handleDelete = (record: ASN) => {
    deleteMutation.mutate(record.id);
  };

  /** 行操作菜单 */
  const rowMenuItems = (record: ASN): MenuProps['items'] => [
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
          content: `确定要删除 AS${record.asn} (${record.name}) 吗？`,
          okType: 'danger',
          okText: '删除',
          cancelText: '取消',
          onOk: () => handleDelete(record),
        }),
    },
  ];

  /** 表格列定义 */
  const columns: ColumnsType<ASN> = useMemo(
    () => [
      {
        title: 'ASN',
        dataIndex: 'asn',
        key: 'asn',
        width: 120,
        render: (v: number) => <Text strong>AS{v}</Text>,
      },
      {
        title: '名称',
        dataIndex: 'name',
        key: 'name',
        width: 180,
        ellipsis: true,
      },
      {
        title: '类型',
        dataIndex: 'type',
        key: 'type',
        width: 110,
        render: (v: string) => <Tag color={TYPE_COLOR[v] || 'default'}>{v}</Tag>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>,
      },
      {
        title: '联系人',
        dataIndex: 'contact',
        key: 'contact',
        width: 120,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: '邮箱',
        dataIndex: 'email',
        key: 'email',
        width: 180,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: '风险画像',
        dataIndex: 'risk_profile',
        key: 'risk_profile',
        width: 110,
        render: (v: string) => <Tag color={RISK_COLOR[v] || 'default'}>{v}</Tag>,
      },
      {
        title: '关系标签',
        dataIndex: 'relationship_tags',
        key: 'relationship_tags',
        width: 180,
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
      title="ASN 管理"
      subtitle="管理自治系统号（ASN）及关联联系信息"
      extra={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isFetching} />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建 ASN
          </Button>
        </Space>
      }
    >
      <SearchBar
        placeholder="搜索 ASN 号、名称、联系人..."
        value={searchText}
        onChange={setSearchText}
        onSearch={handleSearch}
        searchWidth={300}
        filters={[
          {
            key: 'type',
            node: (
              <Select
                allowClear
                placeholder="类型"
                style={{ width: 120 }}
                options={TYPE_OPTIONS}
                value={queryParams.type}
                onChange={(v) => handleFilterChange('type', v)}
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
            key: 'risk',
            node: (
              <Select
                allowClear
                placeholder="风险画像"
                style={{ width: 140 }}
                options={RISK_OPTIONS}
                value={queryParams.risk_profile}
                onChange={(v) => handleFilterChange('risk_profile', v)}
              />
            ),
          },
        ]}
      />

      <Table<ASN>
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
                <Text type="secondary">NOC 电话：</Text>
                {record.noc_phone || '-'}
              </span>
              <span>
                <Text type="secondary">应急联系：</Text>
                {record.emergency_contact || '-'}
              </span>
              <span>
                <Text type="secondary">创建时间：</Text>
                {record.created_at}
              </span>
              {record.description && (
                <span>
                  <Text type="secondary">描述：</Text>
                  {record.description}
                </span>
              )}
            </Space>
          ),
        }}
      />

      <ASNForm
        open={formOpen}
        asn={editingASN}
        onClose={() => setFormOpen(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['asns'] });
        }}
      />
    </PageContainer>
  );
}

export default ASNs;
