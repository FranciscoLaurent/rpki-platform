// 资产管理相关 API 调用
import { get } from './client';

/** 一致性检查严重程度 */
export type ConsistencySeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

/** 一致性检查项 */
export interface ConsistencyIssue {
  id: number;
  type: string;
  prefix: string;
  description: string;
  severity: string;
  detected_at: string;
  recommendation: string | null;
}

/** 一致性检查结果 */
export interface ConsistencyCheckResult {
  total_issues: number;
  by_severity: Record<string, number>;
  issues: ConsistencyIssue[];
  checked_at: string;
}

/** 关系视图节点类型 */
export interface RelationshipView {
  prefix_id: number;
  prefix: string;
  asns: Array<{
    id: number;
    asn: number;
    name: string;
    type: string;
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
  business_services: string[];
  events: Array<{
    id: number;
    type: string;
    severity: string;
    message: string;
    created_at: string;
  }>;
}

/** 执行一致性检查 */
export function consistencyCheck(): Promise<ConsistencyCheckResult> {
  return get<ConsistencyCheckResult>('/assets/consistency-check');
}

/** 获取关系视图 */
export function getRelationshipView(prefixId: number): Promise<RelationshipView> {
  return get<RelationshipView>(`/assets/relationships/${prefixId}`);
}
