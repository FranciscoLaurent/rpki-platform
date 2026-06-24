// 系统设置页面：用户管理 / 租户管理 / API Key / 审计日志
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Empty, Select, Space, Table, Tabs, Tag } from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import {
  getAPIKeys,
  getAuditLogs,
  getTenants,
  getUsers,
} from '@/api/settings';
import type { APIKey, AuditLog, Tenant, User } from '@/api/settings';

/** 用户行类型（扩展 last_login 字段，后端返回但类型未声明） */
interface UserRow extends User {
  last_login?: string | null;
}

/** 审计日志动作选项 */
const ACTION_OPTIONS = [
  { label: '登录成功', value: 'login_success' },
  { label: '登录失败', value: 'login_failed' },
  { label: '登出', value: 'logout' },
  { label: '修改密码', value: 'change_password' },
  { label: '创建用户', value: 'create_user' },
  { label: '更新用户', value: 'update_user' },
  { label: '删除用户', value: 'delete_user' },
  { label: '创建 API Key', value: 'create_api_key' },
  { label: '撤销 API Key', value: 'revoke_api_key' },
];

/** 资源类型选项 */
const RESOURCE_TYPE_OPTIONS = [
  { label: '用户', value: 'user' },
  { label: '租户', value: 'tenant' },
  { label: 'API Key', value: 'api_key' },
  { label: '角色', value: 'role' },
];

/** 格式化时间，空值返回 '-' */
function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss');
}

/** 计算 API Key 状态标签（active/revoked/expired） */
function getAPIKeyStatus(key: APIKey): { label: string; color: string } {
  if (!key.is_active) return { label: 'revoked', color: 'red' };
  if (key.expires_at && dayjs(key.expires_at).isBefore(dayjs())) {
    return { label: 'expired', color: 'default' };
  }
  return { label: 'active', color: 'green' };
}

/** 用户表格列定义 */
const userColumns: ColumnsType<UserRow> = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '邮箱', dataIndex: 'email', key: 'email' },
  {
    title: '姓名',
    dataIndex: 'full_name',
    key: 'full_name',
    render: (v: string | null) => v || '-',
  },
  {
    title: '超级管理员',
    dataIndex: 'is_superuser',
    key: 'is_superuser',
    render: (v: boolean) => (
      <Tag color={v ? 'red' : 'default'}>{v ? '是' : '否'}</Tag>
    ),
  },
  {
    title: '状态',
    dataIndex: 'is_active',
    key: 'is_active',
    render: (v: boolean) => (
      <Tag color={v ? 'green' : 'default'}>{v ? 'active' : 'inactive'}</Tag>
    ),
  },
  {
    title: '最后登录',
    dataIndex: 'last_login',
    key: 'last_login',
    render: formatTime,
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    render: formatTime,
  },
];

/** 租户表格列定义 */
const tenantColumns: ColumnsType<Tenant> = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: 'slug', dataIndex: 'slug', key: 'slug' },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    render: (v: string) => (
      <Tag color={v === 'active' ? 'green' : 'default'}>{v}</Tag>
    ),
  },
  { title: '最大用户数', dataIndex: 'max_users', key: 'max_users' },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    render: formatTime,
  },
];

/** API Key 表格列定义 */
const apiKeyColumns: ColumnsType<APIKey> = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '前缀', dataIndex: 'key_prefix', key: 'key_prefix' },
  {
    title: '权限范围',
    dataIndex: 'scopes',
    key: 'scopes',
    render: (scopes: string[]) =>
      scopes.length ? (
        <Space size={4} wrap>
          {scopes.map((s) => (
            <Tag key={s}>{s}</Tag>
          ))}
        </Space>
      ) : (
        '-'
      ),
  },
  {
    title: '状态',
    key: 'status',
    render: (_, record) => {
      const status = getAPIKeyStatus(record);
      return <Tag color={status.color}>{status.label}</Tag>;
    },
  },
  {
    title: '过期时间',
    dataIndex: 'expires_at',
    key: 'expires_at',
    render: formatTime,
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    render: formatTime,
  },
];

/** 审计日志表格列定义 */
const auditLogColumns: ColumnsType<AuditLog> = [
  {
    title: '时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180,
    render: formatTime,
  },
  {
    title: '动作',
    dataIndex: 'action',
    key: 'action',
    width: 160,
    render: (v: string) => <Tag color="blue">{v}</Tag>,
  },
  {
    title: '资源类型',
    dataIndex: 'resource_type',
    key: 'resource_type',
    width: 120,
    render: (v: string | null) => v || '-',
  },
  {
    title: '用户 ID',
    dataIndex: 'user_id',
    key: 'user_id',
    width: 100,
    render: (v: number | null) => v ?? '-',
  },
  {
    title: 'IP',
    dataIndex: 'ip_address',
    key: 'ip_address',
    width: 140,
    render: (v: string | null) => v || '-',
  },
  {
    title: 'User-Agent',
    dataIndex: 'user_agent',
    key: 'user_agent',
    ellipsis: true,
    render: (v: string | null) => v || '-',
  },
  {
    title: '详情',
    dataIndex: 'details',
    key: 'details',
    ellipsis: true,
    render: (v: Record<string, unknown> | null) => (v ? JSON.stringify(v) : '-'),
  },
];

/** 系统设置页面 */
function Settings() {
  const [activeTab, setActiveTab] = useState('users');

  // 用户管理数据（按需加载）
  const usersQuery = useQuery({
    queryKey: ['settings-users'],
    queryFn: () => getUsers({ limit: 100 }),
    enabled: activeTab === 'users',
  });

  // 租户管理数据（按需加载）
  const tenantsQuery = useQuery({
    queryKey: ['settings-tenants'],
    queryFn: () => getTenants({ limit: 200 }),
    enabled: activeTab === 'tenants',
  });

  // API Key 数据（按需加载）
  const apiKeysQuery = useQuery({
    queryKey: ['settings-api-keys'],
    queryFn: () => getAPIKeys({ limit: 200 }),
    enabled: activeTab === 'api-keys',
  });

  // 审计日志过滤与分页状态
  const [auditAction, setAuditAction] = useState<string | undefined>(undefined);
  const [auditResourceType, setAuditResourceType] = useState<string | undefined>(undefined);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(10);

  const auditLogsQuery = useQuery({
    queryKey: [
      'settings-audit-logs',
      auditAction,
      auditResourceType,
      auditPage,
      auditPageSize,
    ],
    queryFn: () =>
      getAuditLogs({
        action: auditAction,
        resource_type: auditResourceType,
        skip: (auditPage - 1) * auditPageSize,
        limit: auditPageSize,
      }),
    enabled: activeTab === 'audit-logs',
  });

  /** 审计日志分页配置 */
  const auditPagination: TablePaginationConfig = {
    current: auditPage,
    pageSize: auditPageSize,
    total: auditLogsQuery.data?.total ?? 0,
    showSizeChanger: true,
    showTotal: (total) => `共 ${total} 条`,
    onChange: (page, pageSize) => {
      setAuditPage(page);
      setAuditPageSize(pageSize);
    },
  };

  /** Tab 项配置 */
  const tabItems = [
    {
      key: 'users',
      label: '用户管理',
      children: (
        <Table<UserRow>
          rowKey="id"
          columns={userColumns}
          dataSource={usersQuery.data ?? []}
          loading={usersQuery.isLoading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: <Empty description="暂无用户" /> }}
        />
      ),
    },
    {
      key: 'tenants',
      label: '租户管理',
      children: (
        <Table<Tenant>
          rowKey="id"
          columns={tenantColumns}
          dataSource={tenantsQuery.data?.items ?? []}
          loading={tenantsQuery.isLoading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: <Empty description="暂无租户" /> }}
        />
      ),
    },
    {
      key: 'api-keys',
      label: 'API Key',
      children: (
        <Table<APIKey>
          rowKey="id"
          columns={apiKeyColumns}
          dataSource={apiKeysQuery.data?.items ?? []}
          loading={apiKeysQuery.isLoading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: <Empty description="暂无 API Key" /> }}
        />
      ),
    },
    {
      key: 'audit-logs',
      label: '审计日志',
      children: (
        <>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space wrap>
              <Select
                allowClear
                placeholder="动作"
                style={{ width: 200 }}
                options={ACTION_OPTIONS}
                value={auditAction}
                onChange={(v) => {
                  setAuditAction(v);
                  setAuditPage(1);
                }}
              />
              <Select
                allowClear
                placeholder="资源类型"
                style={{ width: 200 }}
                options={RESOURCE_TYPE_OPTIONS}
                value={auditResourceType}
                onChange={(v) => {
                  setAuditResourceType(v);
                  setAuditPage(1);
                }}
              />
            </Space>
          </Card>
          <Table<AuditLog>
            rowKey="id"
            columns={auditLogColumns}
            dataSource={auditLogsQuery.data?.items ?? []}
            loading={auditLogsQuery.isLoading}
            pagination={auditPagination}
            locale={{ emptyText: <Empty description="暂无审计日志" /> }}
          />
        </>
      ),
    },
  ];

  return (
    <PageContainer
      title="系统设置"
      subtitle="管理平台用户、租户、API Key 与审计日志"
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </PageContainer>
  );
}

export default Settings;
