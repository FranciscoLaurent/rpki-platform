// RPKI 仓库同步与验证相关 API 调用
import { get, post } from './client';

/** TAL（信任锚定位器） */
export interface TAL {
  id: number;
  name: string;
  uri: string;
  rsync_uri: string;
  raw_tal: string;
  status: string;
  last_synced_at: string | null;
  sync_status: string;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

/** VRP（可验证路由声明） */
export interface VRP {
  id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  origin_as: number;
  max_length: number | null;
  tal_id: number | null;
  roa_id: number | null;
  trust_anchor: string | null;
  validation_status: string;
  created_at: string;
  updated_at: string;
}

/** 仓库健康状态 */
export interface RepositoryHealth {
  repository_id: number;
  status: string;
  sync_status: string;
  last_synced_at: string | null;
  object_count: number;
  last_error: string | null;
  is_healthy: boolean;
}

/** RPKI 整体健康状态 */
export interface RPKIHealth {
  overall_healthy: boolean;
  total_repositories: number;
  healthy_repositories: number;
  failed_repositories: number;
  repositories: RepositoryHealth[];
  cache_status: Record<string, unknown> | null;
}

/** 同步状态 */
export interface SyncStatus {
  tal_id: number | null;
  status: string;
  progress: number;
  last_synced_at: string | null;
  error: string | null;
}

/** VRP 查询参数 */
export interface VRPQueryParams {
  prefix?: string;
  origin_as?: number;
  max_length?: number;
  tal_id?: number;
  skip?: number;
  limit?: number;
}

/** 同步触发响应 */
export interface SyncTriggerResult {
  message: string;
  tal_id: number | null;
  status: string;
}

/** 获取 TAL 列表 */
export function getTALs(
  params: { skip?: number; limit?: number } = {},
): Promise<{ items: TAL[]; total: number }> {
  return get<{ items: TAL[]; total: number }>('/rpki/tals', { params });
}

/** 获取 VRP 列表（支持前缀过滤与分页） */
export function getVRPs(
  params: VRPQueryParams = {},
): Promise<{ items: VRP[]; total: number }> {
  return get<{ items: VRP[]; total: number }>('/rpki/vrps', { params });
}

/** 获取 RPKI 整体健康状态 */
export function getRPKIHealth(): Promise<RPKIHealth> {
  return get<RPKIHealth>('/rpki/health');
}

/** 触发所有活跃仓库同步 */
export function triggerSync(): Promise<SyncTriggerResult> {
  return post<SyncTriggerResult>('/rpki/sync-all');
}
