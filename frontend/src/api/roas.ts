// ROA 生命周期管理相关 API 调用
import { get } from './client';

/** ROA */
export interface ROA {
  id: number;
  object_id: number;
  prefix: string;
  prefix_family: number;
  prefix_length: number;
  origin_as: number;
  max_length: number | null;
  tal_id: number | null;
  status: string;
  not_before: string | null;
  not_after: string | null;
  created_at: string;
  updated_at: string;
}

/** 按重要度分级的覆盖率统计 */
export interface ROACoverageByImportance {
  importance: string;
  total_prefixes: number;
  covered_prefixes: number;
  coverage_rate: number;
}

/** 按验证状态分组的公告统计 */
export interface ROACoverageByStatus {
  validation_status: string;
  count: number;
}

/** ROA 覆盖率统计 */
export interface ROACoverage {
  total_prefixes: number;
  covered_prefixes: number;
  coverage_rate: number;
  total_announcements: number;
  by_importance: ROACoverageByImportance[];
  by_status: ROACoverageByStatus[];
}

/** ROA 缺失检测结果 */
export interface ROAMissingResult {
  prefix: string;
  origin_as: number;
  has_roa: boolean;
  has_vrp: boolean;
  validation_status: string;
  importance: string | null;
  business_service: string | null;
  customer_id: number | null;
}

/** ROA 冲突检测结果 */
export interface ROAConflictResult {
  prefix: string;
  origin_as: number | null;
  conflicting_roas: ROA[];
  conflict_type: string;
  description: string;
}

/** ROA 健康度摘要 */
export interface ROAHealth {
  total_roas: number;
  valid_roas: number;
  expired_roas: number;
  revoked_roas: number;
  coverage_rate: number;
  missing_count: number;
  conflict_count: number;
  high_risk_count: number;
  overall_healthy: boolean;
  summary: Record<string, unknown>;
}

/** ROA 查询参数 */
export interface ROAQueryParams {
  prefix?: string;
  origin_as?: number;
  max_length?: number;
  status?: string;
  tal_id?: number;
  page?: number;
  page_size?: number;
}

/** 查询 ROA 列表（支持分页、前缀、origin_as、status 过滤） */
export function getROAs(
  params: ROAQueryParams = {},
): Promise<{ items: ROA[]; total: number }> {
  return get<{ items: ROA[]; total: number }>('/roas', { params });
}

/** 获取 ROA 覆盖率统计 */
export function getROACoverage(): Promise<ROACoverage> {
  return get<ROACoverage>('/roas/coverage-stats');
}

/** ROA 缺失检测 */
export function checkROAMissing(): Promise<ROAMissingResult[]> {
  return get<ROAMissingResult[]>('/roas/missing-check');
}

/** ROA 冲突检测 */
export function checkROAConflicts(): Promise<ROAConflictResult[]> {
  return get<ROAConflictResult[]>('/roas/conflict-check');
}

/** 获取 ROA 健康度摘要 */
export function getROAHealth(): Promise<ROAHealth> {
  return get<ROAHealth>('/roas/health-summary');
}
