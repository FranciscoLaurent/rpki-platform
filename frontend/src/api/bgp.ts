// BGP 数据采集与监测相关 API 调用
import { get } from './client';

/** BGP 数据源 */
export interface BGPSource {
  id: number;
  name: string;
  source_type: string;
  protocol: string;
  endpoint: string;
  credentials: Record<string, unknown> | null;
  trust_level: string;
  coverage: Record<string, unknown> | null;
  config: Record<string, unknown> | null;
  status: string;
  last_connected_at: string | null;
  last_error: string | null;
  tenant_id: number | null;
  created_at: string;
  updated_at: string;
}

/** 观察点 */
export interface ObservationPoint {
  id: number;
  name: string;
  data_source_id: number;
  location: string | null;
  collector_id: string | null;
  ip_version: string;
  status: string;
  created_at: string;
  updated_at: string;
}

/** BGP 公告 */
export interface BGPAnnouncement {
  id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  origin_as: number | null;
  as_path: number[] | null;
  next_hop: string | null;
  communities: string[] | null;
  large_communities: string[] | null;
  med: number | null;
  local_pref: number | null;
  observation_point_id: number | null;
  data_source_id: number | null;
  timestamp: string;
  address_family: number;
  rpki_validation_status: string | null;
  rpki_invalid_reason: string | null;
  created_at: string;
}

/** BGP 撤路 */
export interface BGPWithdraw {
  id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  observation_point_id: number | null;
  data_source_id: number | null;
  timestamp: string;
  created_at: string;
}

/** BGP 统计数据 */
export interface BGPStats {
  total_data_sources: number;
  active_data_sources: number;
  total_observation_points: number;
  total_announcements: number;
  total_withdraws: number;
  total_device_adapters: number;
  announcements_by_rpki_status: Record<string, number>;
}

/** BGP 公告查询参数 */
export interface BGPAnnouncementQueryParams {
  prefix?: string;
  origin_as?: number;
  observation_point_id?: number;
  data_source_id?: number;
  start_time?: string;
  end_time?: string;
  rpki_validation_status?: string;
  skip?: number;
  limit?: number;
}

/** BGP 撤路查询参数 */
export interface BGPWithdrawQueryParams {
  prefix?: string;
  observation_point_id?: number;
  data_source_id?: number;
  start_time?: string;
  end_time?: string;
  skip?: number;
  limit?: number;
}

/** 获取 BGP 数据源列表 */
export function getBGPSources(
  params: { skip?: number; limit?: number; status?: string; source_type?: string } = {},
): Promise<BGPSource[]> {
  return get<BGPSource[]>('/bgp/data-sources', { params });
}

/** 获取观察点列表 */
export function getObservationPoints(
  params: { data_source_id?: number; skip?: number; limit?: number } = {},
): Promise<ObservationPoint[]> {
  return get<ObservationPoint[]>('/bgp/observation-points', { params });
}

/** 查询 BGP 公告列表（支持分页、前缀、origin_as、验证状态过滤） */
export function getBGPAnnouncements(
  params: BGPAnnouncementQueryParams = {},
): Promise<BGPAnnouncement[]> {
  return get<BGPAnnouncement[]>('/bgp/announcements', { params });
}

/** 查询 BGP 撤路列表 */
export function getBGPWithdraws(
  params: BGPWithdrawQueryParams = {},
): Promise<BGPWithdraw[]> {
  return get<BGPWithdraw[]>('/bgp/withdraws', { params });
}

/** 获取 BGP 统计数据 */
export function getBGPStats(): Promise<BGPStats> {
  return get<BGPStats>('/bgp/stats');
}
