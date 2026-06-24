import { get, post } from './client';
import type { LoginParams, TokenInfo, User } from '@/types';

/** 认证相关 API */
export const authApi = {
  /** 用户登录 */
  login: (params: LoginParams) => post<TokenInfo>('/auth/login', params),
  /** 用户登出 */
  logout: () => post('/auth/logout'),
  /** 刷新令牌 */
  refresh: () => post<TokenInfo>('/auth/refresh'),
  /** 获取当前用户信息 */
  me: () => get<User>('/auth/me'),
};

/** 健康检查 API */
export const healthApi = {
  /** 基础健康检查 */
  check: () => get<{ status: string }>('/health'),
  /** 数据库健康检查 */
  checkDb: () => get<{ status: string; component: string }>('/health/db'),
};

export { default as client } from './client';

