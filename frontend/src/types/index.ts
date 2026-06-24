/** 通用 API 响应结构 */
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

/** 分页响应结构 */
export interface PaginatedResponse<T = unknown> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** 用户信息 */
export interface User {
  id: string;
  username: string;
  email?: string;
  role?: string;
}

/** 登录请求参数 */
export interface LoginParams {
  username: string;
  password: string;
}

/** 令牌响应 */
export interface TokenInfo {
  access_token: string;
  token_type: string;
}
