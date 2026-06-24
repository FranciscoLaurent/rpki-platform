// 前缀关系视图：展示前缀—ASN—ROA—BGP—业务—事件关联
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Card,
  Col,
  Descriptions,
  Empty,
  List,
  Row,
  Spin,
  Tag,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import { getPrefixRelationships } from '@/api/prefixes';

const { Title, Text } = Typography;

interface RelationshipViewProps {
  /** 前缀 ID */
  prefixId: number | null;
}

/** 状态颜色映射 */
const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  established: 'green',
  idle: 'default',
  down: 'red',
  conflict: 'red',
};

/** 严重程度颜色映射 */
const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'blue',
  info: 'default',
};

/** 关系视图组件 */
function RelationshipView({ prefixId }: RelationshipViewProps) {
  const enabled = prefixId !== null;

  const { data, isLoading, error } = useQuery({
    queryKey: ['prefix-relationships', prefixId],
    queryFn: () => getPrefixRelationships(prefixId as number),
    enabled,
  });

  if (!enabled) {
    return (
      <Card>
        <Empty description="请从列表中选择前缀以查看关系视图" />
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="加载关系视图..." />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Alert
          type="error"
          message="加载关系视图失败"
          description={(error as Error).message}
        />
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div>
      {/* 前缀基本信息 */}
      <Card style={{ marginBottom: 16 }}>
        <Title level={5} style={{ marginTop: 0 }}>
          前缀基本信息
        </Title>
        <Descriptions column={{ xs: 1, sm: 2, lg: 3 }} bordered size="small">
          <Descriptions.Item label="前缀">{data.prefix.prefix}</Descriptions.Item>
          <Descriptions.Item label="地址族">IPv{data.prefix.prefix_family}</Descriptions.Item>
          <Descriptions.Item label="前缀长度">{data.prefix.prefix_length}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[data.prefix.status] || 'default'}>
              {data.prefix.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="重要性">{data.prefix.importance}</Descriptions.Item>
          <Descriptions.Item label="业务归属">
            {data.prefix.business_service || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="地域">{data.prefix.region || '-'}</Descriptions.Item>
          <Descriptions.Item label="父前缀 ID">
            {data.parent ? data.parent.prefix : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="子前缀数">{data.children?.length || 0}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={[16, 16]}>
        {/* 关联 ASN */}
        <Col xs={24} lg={12}>
          <Card title="关联 ASN" size="small">
            {data.asns?.length ? (
              <List
                size="small"
                dataSource={data.asns}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <span>
                          <Text strong>AS{item.asn}</Text>
                          <Tag style={{ marginLeft: 8 }}>{item.name}</Tag>
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="无关联 ASN" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* BGP 邻居 */}
        <Col xs={24} lg={12}>
          <Card title="BGP 邻居" size="small">
            {data.bgp_peers?.length ? (
              <List
                size="small"
                dataSource={data.bgp_peers}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <span>
                          <Text strong>{item.peer_ip}</Text>
                          <Tag style={{ marginLeft: 8 }}>AS{item.remote_asn}</Tag>
                          <Tag
                            color={STATUS_COLOR[item.status] || 'default'}
                            style={{ marginLeft: 4 }}
                          >
                            {item.status}
                          </Tag>
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="无 BGP 邻居" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* ROA 记录 */}
        <Col xs={24} lg={12}>
          <Card title="ROA 记录" size="small">
            {data.roas?.length ? (
              <List
                size="small"
                dataSource={data.roas}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <span>
                          <Text strong>AS{item.asn}</Text>
                          <Tag style={{ marginLeft: 8 }}>maxLength: {item.max_length}</Tag>
                          <Tag
                            color={item.valid ? 'green' : 'red'}
                            style={{ marginLeft: 4 }}
                          >
                            {item.valid ? '有效' : '无效'}
                          </Tag>
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="无 ROA 记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* 子前缀 */}
        <Col xs={24} lg={12}>
          <Card title={`子前缀 (${data.children?.length || 0})`} size="small">
            {data.children?.length ? (
              <List
                size="small"
                dataSource={data.children}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <span>
                          <Text strong>{item.prefix}</Text>
                          <Tag
                            color={STATUS_COLOR[item.status] || 'default'}
                            style={{ marginLeft: 8 }}
                          >
                            {item.status}
                          </Tag>
                        </span>
                      }
                      description={item.business_service || item.description || '-'}
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="无子前缀" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* 关联事件 */}
        <Col xs={24}>
          <Card title="关联事件" size="small">
            {data.events?.length ? (
              <List
                size="small"
                dataSource={data.events}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <span>
                          <Tag color={SEVERITY_COLOR[item.severity] || 'default'}>
                            {item.severity}
                          </Tag>
                          <Text strong style={{ marginLeft: 8 }}>
                            {item.type}
                          </Text>
                        </span>
                      }
                      description={
                        <span>
                          {item.message}
                          <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                            {dayjs(item.created_at).format('YYYY-MM-DD HH:mm:ss')}
                          </Text>
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="无关联事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default RelationshipView;
