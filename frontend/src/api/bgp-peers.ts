// BGP 邻居相关 API 调用
import { del, get, post, put } from './client';

/** BGP 会话类型枚举 */
export type BGPSessionType = 'ebgp' | 'ibgp' | 'rr-client' | 'rs-client';

/** BGP 会话状态枚举 */
export type BGPSessionStatus = 'established' | 'idle' | 'active' | 'connect' | 'down';

/** BGP 邻居实体 */
export interface BGPPeer {
  id: number;
  peer_ip: string;
  remote_asn: number;
  address_family: number;
  session_type: string;
  status: string;
  route_policy: string | null;
  max_prefixes: number;
  description: string | null;
  created_at: string;
  updated_at: string;
}

/** BGP 邻居创建参数 */
export interface BGPPeerCreate {
  peer_ip: string;
  remote_asn: number;
  address_family?: number;
  session_type?: string;
  route_policy?: string;
  max_prefixes?: number;
  description?: string;
}

/** BGP 邻居更新参数 */
export interface BGPPeerUpdate extends Partial<BGPPeerCreate> {}

/** BGP 邻居查询参数 */
export interface BGPPeerQueryParams {
  page?: number;
  page_size?: number;
  remote_asn?: number;
  address_family?: number;
  session_type?: string;
  status?: string;
  search?: string;
}

/** 分页响应 */
export interface BGPPeerPaginated {
  items: BGPPeer[];
  total: number;
  page: number;
  page_size: number;
}

/** 获取 BGP 邻居列表 */
export function getBGPPeers(params: BGPPeerQueryParams = {}): Promise<BGPPeerPaginated> {
  return get<BGPPeerPaginated>('/bgp-peers', { params });
}

/** 获取 BGP 邻居详情 */
export function getBGPPeer(id: number): Promise<BGPPeer> {
  return get<BGPPeer>(`/bgp-peers/${id}`);
}

/** 创建 BGP 邻居 */
export function createBGPPeer(data: BGPPeerCreate): Promise<BGPPeer> {
  return post<BGPPeer>('/bgp-peers', data);
}

/** 更新 BGP 邻居 */
export function updateBGPPeer(id: number, data: BGPPeerUpdate): Promise<BGPPeer> {
  return put<BGPPeer>(`/bgp-peers/${id}`, data);
}

/** 删除 BGP 邻居 */
export function deleteBGPPeer(id: number): Promise<void> {
  return del<void>(`/bgp-peers/${id}`);
}
