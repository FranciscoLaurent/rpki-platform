// 系统设置（用户、租户、API Key、审计日志）相关 API 调用
import { get } from './client';

/** 角色 */
export interface Role {
  id: number;
  name: string;
  code: string;
  permissions: string[];
}

/** 用户 */
export interface User {
  id: number;
  email: string;
  username: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  roles: Role[];
  created_at: string;
  must_change_password: boolean;
}

/** 租户 */
export interface Tenant {
  id: number;
  name: string;
  slug: string;
  status: string;
  settings: Record<string, unknown>;
  max_users: number;
  created_at: string;
  updated_at: string;
}

/** API Key */
export interface APIKey {
  id: number;
  name: string;
  key_prefix: string;
  user_id: number;
  tenant_id: number | null;
  scopes: string[];
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 审计日志 */
export interface AuditLog {
  id: number;
  user_id: number | null;
  tenant_id: number | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  request_id: string | null;
  created_at: string;
}

/** 审计日志查询参数 */
export interface AuditLogQueryParams {
  user_id?: number;
  tenant_id?: number;
  action?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number;
}

/** 获取用户列表 */
export function getUsers(
  params: { skip?: number; limit?: number } = {},
): Promise<User[]> {
  return get<User[]>('/users', { params });
}

/** 获取租户列表 */
export function getTenants(
  params: { skip?: number; limit?: number; status?: string; name?: string } = {},
): Promise<{ items: Tenant[]; total: number }> {
  return get<{ items: Tenant[]; total: number }>('/tenants', { params });
}

/** 获取 API Key 列表 */
export function getAPIKeys(
  params: { is_active?: boolean; skip?: number; limit?: number } = {},
): Promise<{ items: APIKey[]; total: number }> {
  return get<{ items: APIKey[]; total: number }>('/api-keys', { params });
}

/** 查询审计日志（支持分页、动作、资源类型过滤） */
export function getAuditLogs(
  params: AuditLogQueryParams = {},
): Promise<{ items: AuditLog[]; total: number }> {
  return get<{ items: AuditLog[]; total: number }>('/audit-logs', { params });
}
