// 路由安全检测引擎相关 API 调用
import { get, post, put } from './client';

/** 检测规则 */
export interface DetectionRule {
  id: number;
  name: string;
  code: string;
  description: string | null;
  rule_type: string;
  enabled: boolean;
  priority: number;
  conditions: Record<string, unknown> | null;
  thresholds: Record<string, unknown> | null;
  whitelist: Record<string, unknown> | null;
  scope: Record<string, unknown> | null;
  severity: string;
  tenant_id: number | null;
  created_at: string;
  updated_at: string;
}

/** 告警 */
export interface Alert {
  id: number;
  rule_id: number | null;
  alert_type: string;
  severity: string;
  prefix: string;
  origin_as: number | null;
  as_path: number[] | null;
  observation_point_id: number | null;
  title: string;
  description: string | null;
  evidence: Record<string, unknown> | null;
  risk_score: number;
  confidence: number;
  status: string;
  is_benign_conflict: boolean;
  benign_conflict_type: string | null;
  incident_id: number | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  tenant_id: number | null;
  created_at: string;
  updated_at: string;
}

/** 事件 */
export interface Incident {
  id: number;
  title: string;
  description: string | null;
  severity: string;
  status: string;
  alert_ids: number[] | null;
  affected_prefixes: string[] | null;
  affected_asns: number[] | null;
  assigned_to: number | null;
  root_cause: string | null;
  resolution: string | null;
  evidence: Record<string, unknown> | null;
  timeline: Array<Record<string, unknown>> | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  tenant_id: number | null;
  created_at: string;
  updated_at: string;
}

/** 告警查询参数 */
export interface AlertQueryParams {
  prefix?: string;
  origin_as?: number;
  severity?: string;
  status?: string;
  alert_type?: string;
  incident_id?: number;
  start_time?: string;
  end_time?: string;
  skip?: number;
  limit?: number;
}

/** 事件查询参数 */
export interface IncidentQueryParams {
  status?: string;
  severity?: string;
  assigned_to?: number;
  prefix?: string;
  asn?: number;
  start_time?: string;
  end_time?: string;
  skip?: number;
  limit?: number;
}

/** 事件关闭请求 */
export interface IncidentCloseData {
  resolution: string;
}

/** 获取检测规则列表 */
export function getDetectionRules(
  params: { rule_type?: string; enabled?: boolean; severity?: string; skip?: number; limit?: number } = {},
): Promise<DetectionRule[]> {
  return get<DetectionRule[]>('/detection/rules', { params });
}

/** 查询告警列表（支持分页、状态、严重等级过滤） */
export function getAlerts(
  params: AlertQueryParams = {},
): Promise<Alert[]> {
  return get<Alert[]>('/detection/alerts', { params });
}

/** 查询事件列表（支持分页、状态过滤） */
export function getIncidents(
  params: IncidentQueryParams = {},
): Promise<Incident[]> {
  return get<Incident[]>('/detection/incidents', { params });
}

/** 更新告警处置状态 */
export function updateAlertStatus(
  id: number,
  status: string,
): Promise<Alert> {
  return put<Alert>(`/detection/alerts/${id}/status`, { status });
}

/** 关联告警到事件 */
export function assignAlert(
  id: number,
  incidentId: number,
): Promise<Alert> {
  return post<Alert>(`/detection/alerts/${id}/assign`, { incident_id: incidentId });
}

/** 关闭事件 */
export function closeIncident(
  id: number,
  data: IncidentCloseData,
): Promise<Incident> {
  return post<Incident>(`/detection/incidents/${id}/close`, data);
}
