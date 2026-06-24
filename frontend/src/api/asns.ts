// ASN 相关 API 调用
import { del, get, post, put } from './client';

/** ASN 类型枚举 */
export type ASNType = 'transit' | 'customer' | 'peer' | 'internal';

/** ASN 状态枚举 */
export type ASNStatus = 'active' | 'suspended' | 'deprecated';

/** ASN 风险画像枚举 */
export type ASNRiskProfile = 'low' | 'medium' | 'high' | 'critical';

/** ASN 实体 */
export interface ASN {
  id: number;
  asn: number;
  name: string;
  type: string;
  status: string;
  contact: string | null;
  email: string | null;
  noc_phone: string | null;
  emergency_contact: string | null;
  relationship_tags: string[];
  risk_profile: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

/** ASN 创建参数 */
export interface ASNCreate {
  asn: number;
  name: string;
  type?: string;
  status?: string;
  contact?: string;
  email?: string;
  noc_phone?: string;
  emergency_contact?: string;
  relationship_tags?: string[];
  risk_profile?: string;
  description?: string;
}

/** ASN 更新参数 */
export interface ASNUpdate extends Partial<ASNCreate> {}

/** ASN 查询参数 */
export interface ASNQueryParams {
  page?: number;
  page_size?: number;
  type?: string;
  status?: string;
  risk_profile?: string;
  search?: string;
}

/** 分页响应 */
export interface ASNPaginated {
  items: ASN[];
  total: number;
  page: number;
  page_size: number;
}

/** 获取 ASN 列表 */
export function getASNs(params: ASNQueryParams = {}): Promise<ASNPaginated> {
  return get<ASNPaginated>('/asns', { params });
}

/** 获取 ASN 详情 */
export function getASN(id: number): Promise<ASN> {
  return get<ASN>(`/asns/${id}`);
}

/** 创建 ASN */
export function createASN(data: ASNCreate): Promise<ASN> {
  return post<ASN>('/asns', data);
}

/** 更新 ASN */
export function updateASN(id: number, data: ASNUpdate): Promise<ASN> {
  return put<ASN>(`/asns/${id}`, data);
}

/** 删除 ASN */
export function deleteASN(id: number): Promise<void> {
  return del<void>(`/asns/${id}`);
}
