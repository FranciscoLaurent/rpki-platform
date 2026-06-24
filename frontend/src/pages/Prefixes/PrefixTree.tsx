// 前缀树展示
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Descriptions, Empty, Spin, Tag, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { getPrefixTree } from '@/api/prefixes';
import type { PrefixTreeNode } from '@/api/prefixes';

const { Text } = Typography;

interface PrefixTreeProps {
  /** 是否显示 */
  open: boolean;
}

/** 状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  reserved: 'blue',
  deprecated: 'default',
  conflict: 'red',
};

/** 重要性颜色映射 */
const IMPORTANCE_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'default',
};

/** 将前缀树转换为 Ant Design Tree 数据节点 */
function buildTreeData(nodes: PrefixTreeNode[]): DataNode[] {
  return nodes.map((node) => ({
    key: node.id,
    title: (
      <span>
        <Text strong>{node.prefix}</Text>
        <Tag color={STATUS_COLOR[node.status] || 'default'} style={{ marginLeft: 8 }}>
          {node.status}
        </Tag>
        {node.business_service && (
          <Tag color={IMPORTANCE_COLOR[node.importance] || 'default'} style={{ marginLeft: 4 }}>
            {node.business_service}
          </Tag>
        )}
      </span>
    ),
    children: node.children?.length ? buildTreeData(node.children) : undefined,
    raw: node,
  })) as DataNode[];
}

/** 前缀树展示组件 */
function PrefixTree({ open }: PrefixTreeProps) {
  const [selected, setSelected] = useState<PrefixTreeNode | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['prefix-tree'],
    queryFn: getPrefixTree,
    enabled: open,
  });

  const treeData = useMemo(() => (data ? buildTreeData(data) : []), [data]);

  if (!open) return null;

  if (isLoading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="加载前缀树..." />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Alert type="error" message="加载前缀树失败" description={(error as Error).message} />
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <Empty description="暂无前缀数据" />
      </Card>
    );
  }

  return (
    <Card>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 50%', minWidth: 320 }}>
          <Typography.Title level={5}>前缀层级关系</Typography.Title>
          <Tree
            treeData={treeData}
            defaultExpandAll
            showLine
            onSelect={(_, info) => {
              const raw = (info.node as unknown as { raw?: PrefixTreeNode }).raw;
              if (raw) setSelected(raw);
            }}
          />
        </div>
        <div style={{ flex: '1 1 40%', minWidth: 320 }}>
          <Typography.Title level={5}>节点详情</Typography.Title>
          {selected ? (
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="前缀">{selected.prefix}</Descriptions.Item>
              <Descriptions.Item label="地址族">
                IPv{selected.prefix_family}
              </Descriptions.Item>
              <Descriptions.Item label="前缀长度">{selected.prefix_length}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLOR[selected.status] || 'default'}>{selected.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="重要性">
                <Tag color={IMPORTANCE_COLOR[selected.importance] || 'default'}>
                  {selected.importance}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="业务归属">
                {selected.business_service || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="地域">{selected.region || '-'}</Descriptions.Item>
              <Descriptions.Item label="机房">{selected.site || '-'}</Descriptions.Item>
              <Descriptions.Item label="云区域">{selected.cloud_zone || '-'}</Descriptions.Item>
              <Descriptions.Item label="标签">
                {selected.tags?.length
                  ? selected.tags.map((t) => <Tag key={t}>{t}</Tag>)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="描述">{selected.description || '-'}</Descriptions.Item>
            </Descriptions>
          ) : (
            <Empty description="点击左侧节点查看详情" />
          )}
        </div>
      </div>
    </Card>
  );
}

export default PrefixTree;
