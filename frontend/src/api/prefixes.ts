// IP 前缀相关 API 调用
import { del, get, post, put } from './client';

/** 前缀状态枚举 */
export type PrefixStatus = 'active' | 'reserved' | 'deprecated' | 'conflict';

/** 前缀重要性枚举 */
export type PrefixImportance = 'critical' | 'high' | 'medium' | 'low';

/** IP 前缀实体 */
export interface Prefix {
  id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  parent_id: number | null;
  status: string;
  importance: string;
  business_service: string | null;
  region: string | null;
  site: string | null;
  cloud_zone: string | null;
  customer_id: number | null;
  tags: string[];
  description: string | null;
  created_at: string;
  updated_at: string;
}

/** 前缀创建参数 */
export interface PrefixCreate {
  prefix: string;
  importance?: string;
  business_service?: string;
  region?: string;
  site?: string;
  cloud_zone?: string;
  customer_id?: number;
  tags?: string[];
  description?: string;
  status?: string;
}

/** 前缀更新参数 */
export interface PrefixUpdate extends Partial<PrefixCreate> {}

/** 前缀树节点 */
export interface PrefixTreeNode extends Prefix {
  children: PrefixTreeNode[];
}

/** 批量导入请求 */
export interface PrefixBatchImport {
  prefixes: PrefixCreate[];
}

/** 批量导入结果 */
export interface PrefixBatchImportResult {
  total: number;
  success: number;
  failed: number;
  errors: string[];
}

/** 前缀查询参数 */
export interface PrefixQueryParams {
  page?: number;
  page_size?: number;
  prefix_family?: number;
  status?: string;
  importance?: string;
  region?: string;
  search?: string;
}

/** 前缀关系视图 */
export interface PrefixRelationship {
  prefix: Prefix;
  parent: Prefix | null;
  children: Prefix[];
  asns: Array<{
    id: number;
    asn: number;
    name: string;
  }>;
  bgp_peers: Array<{
    id: number;
    peer_ip: string;
    remote_asn: number;
    status: string;
  }>;
  roas: Array<{
    id: number;
    asn: number;
    max_length: number;
    valid: boolean;
  }>;
  events: Array<{
    id: number;
    type: string;
    severity: string;
    message: string;
    created_at: string;
  }>;
}

/** 分页响应 */
export interface PrefixPaginated {
  items: Prefix[];
  total: number;
  page: number;
  page_size: number;
}

/** 获取前缀列表 */
export function getPrefixes(params: PrefixQueryParams = {}): Promise<PrefixPaginated> {
  return get<PrefixPaginated>('/prefixes', { params });
}

/** 获取前缀详情 */
export function getPrefix(id: number): Promise<Prefix> {
  return get<Prefix>(`/prefixes/${id}`);
}

/** 创建前缀 */
export function createPrefix(data: PrefixCreate): Promise<Prefix> {
  return post<Prefix>('/prefixes', data);
}

/** 更新前缀 */
export function updatePrefix(id: number, data: PrefixUpdate): Promise<Prefix> {
  return put<Prefix>(`/prefixes/${id}`, data);
}

/** 删除前缀 */
export function deletePrefix(id: number): Promise<void> {
  return del<void>(`/prefixes/${id}`);
}

/** 批量导入前缀 */
export function batchImportPrefixes(
  data: PrefixBatchImport,
): Promise<PrefixBatchImportResult> {
  return post<PrefixBatchImportResult>('/prefixes/batch-import', data);
}

/** 获取前缀树 */
export function getPrefixTree(): Promise<PrefixTreeNode[]> {
  return get<PrefixTreeNode[]>('/prefixes/tree');
}

/** 获取前缀关系视图 */
export function getPrefixRelationships(id: number): Promise<PrefixRelationship> {
  return get<PrefixRelationship>(`/prefixes/${id}/relationships`);
}
