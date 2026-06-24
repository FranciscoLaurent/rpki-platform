// 驾驶舱相关 API 调用
import { get } from './client';

/** 前缀统计信息 */
export interface PrefixStats {
  total: number;
  active: number;
  by_importance: Record<string, number>;
  by_family: Record<string, number>;
}

/** ASN 统计信息 */
export interface ASNStats {
  total: number;
  by_type: Record<string, number>;
}

/** ROA 覆盖率统计 */
export interface ROACoverage {
  total_prefixes: number;
  prefixes_with_roa: number;
  coverage_rate: number;
  missing_count: number;
}

/** BGP 公告 RPKI 验证状态分布 */
export interface ValidationDistribution {
  valid: number;
  invalid: number;
  not_found: number;
  total: number;
}

/** 事件统计信息 */
export interface IncidentStats {
  p0: number;
  p1: number;
  p2: number;
  p3: number;
  p4: number;
  total_open: number;
}

/** RPKI 缓存状态 */
export interface RPKICacheStatus {
  cache_count: number;
  last_update: string | null;
  vrp_count: number;
  status: string;
}

/** BGP 数据源状态 */
export interface BGPSourceStatus {
  active: number;
  error: number;
  total: number;
  by_type: Record<string, number>;
}

/** 风险趋势数据点 */
export interface RiskTrendPoint {
  date: string;
  alert_count: number;
  incident_count: number;
}

/** 驾驶舱总览数据 */
export interface DashboardOverview {
  prefix_stats: PrefixStats;
  asn_stats: ASNStats;
  roa_coverage: ROACoverage;
  validation_distribution: ValidationDistribution;
  incident_stats: IncidentStats;
  rpki_cache_status: RPKICacheStatus;
  bgp_source_status: BGPSourceStatus;
  risk_trend: RiskTrendPoint[];
}

/** 前缀资产属性 */
export interface PrefixAssetInfo {
  id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  status: string;
  importance: string;
  business_service: string | null;
  region: string | null;
  site: string | null;
  cloud_zone: string | null;
  customer_id: number | null;
  tags: string[] | null;
  description: string | null;
  registered_at: string | null;
  expired_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 合法 origin 信息（来自 ROA） */
export interface AuthorizedOrigin {
  roa_id: number;
  origin_as: number;
  prefix: string;
  max_length: number | null;
  tal_id: number | null;
  status: string;
  not_before: string | null;
  not_after: string | null;
}

/** 当前 BGP 公告 */
export interface CurrentAnnouncement {
  id: number;
  prefix: string;
  origin_as: number | null;
  as_path: number[] | null;
  next_hop: string | null;
  observation_point_id: number | null;
  data_source_id: number | null;
  timestamp: string;
  rpki_validation_status: string | null;
  rpki_invalid_reason: string | null;
}

/** 匹配的 VRP */
export interface MatchedVRP {
  id: number;
  prefix: string;
  origin_as: number;
  max_length: number | null;
  tal_id: number | null;
  trust_anchor: string | null;
  validation_status: string;
}

/** 前缀关联告警 */
export interface PrefixAlertItem {
  id: number;
  alert_type: string;
  severity: string;
  title: string;
  description: string | null;
  status: string;
  risk_score: number;
  confidence: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  created_at: string;
}

/** 前缀详情 */
export interface PrefixDetail {
  asset: PrefixAssetInfo;
  authorized_origins: AuthorizedOrigin[];
  current_announcements: CurrentAnnouncement[];
  as_paths: number[][];
  matched_roas: AuthorizedOrigin[];
  matched_vrps: MatchedVRP[];
  irr_info: Record<string, unknown> | null;
  history: Array<Record<string, unknown>>;
  alerts: PrefixAlertItem[];
  business_impact: string | null;
  recommendations: string[];
}

/** ASN 资产属性 */
export interface ASNAssetInfo {
  id: number;
  asn: number;
  name: string;
  asn_type: string;
  status: string;
  risk_profile: string | null;
  contact_name: string | null;
  contact_email: string | null;
  noc_phone: string | null;
  emergency_contact: string | null;
  relationship_tags: string[] | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

/** ASN 关联前缀 */
export interface ASNPrefixItem {
  id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  status: string;
  importance: string;
  business_service: string | null;
}

/** ASN 关联告警 */
export interface ASNAlertItem {
  id: number;
  alert_type: string;
  severity: string;
  prefix: string;
  title: string;
  description: string | null;
  status: string;
  risk_score: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  created_at: string;
}

/** ASN 详情 */
export interface ASNDetail {
  asset: ASNAssetInfo;
  related_prefixes: ASNPrefixItem[];
  upstream: number[];
  downstream: number[];
  peers: number[];
  history_paths: Array<Record<string, unknown>>;
  alerts: ASNAlertItem[];
  risk_profile: string | null;
}

/** 事件时间线条目 */
export interface IncidentTimelineItem {
  timestamp: string;
  event_type: string;
  description: string;
  operator: string | null;
}

/** 事件基本信息 */
export interface IncidentBasicInfo {
  id: number;
  title: string;
  description: string | null;
  severity: string;
  status: string;
  affected_prefixes: string[] | null;
  affected_asns: number[] | null;
  assigned_to: number | null;
  root_cause: string | null;
  resolution: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 事件时间线 */
export interface IncidentTimeline {
  incident: IncidentBasicInfo;
  timeline: IncidentTimelineItem[];
  related_alerts: Array<Record<string, unknown>>;
  impact_scope: Record<string, unknown> | null;
  recommendations: string[];
  root_cause_analysis: string | null;
}

/** 获取总览驾驶舱数据 */
export function getDashboardOverview(): Promise<DashboardOverview> {
  return get<DashboardOverview>('/dashboard/overview');
}

/** 获取前缀详情 */
export function getPrefixDetail(prefixId: number): Promise<PrefixDetail> {
  return get<PrefixDetail>(`/dashboard/prefixes/${prefixId}/detail`);
}

/** 获取 ASN 详情 */
export function getASNDetail(asnId: number): Promise<ASNDetail> {
  return get<ASNDetail>(`/dashboard/asns/${asnId}/detail`);
}

/** 获取事件时间线 */
export function getIncidentTimeline(incidentId: number): Promise<IncidentTimeline> {
  return get<IncidentTimeline>(`/dashboard/incidents/${incidentId}/timeline`);
}
