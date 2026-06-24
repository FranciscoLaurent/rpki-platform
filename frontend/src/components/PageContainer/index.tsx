// 通用页面容器组件
import type { ReactNode } from 'react';
import { Card, Space, Typography } from 'antd';

const { Title, Text } = Typography;

interface PageContainerProps {
  /** 页面标题 */
  title: string;
  /** 页面副标题/描述 */
  subtitle?: string;
  /** 顶部操作按钮区 */
  extra?: ReactNode;
  /** 页面内容 */
  children: ReactNode;
  /** 是否移除内边距（用于全宽表格等场景） */
  bodyPadding?: boolean;
}

/** 通用页面容器：统一标题、操作区与内容区样式 */
function PageContainer({ title, subtitle, extra, children, bodyPadding = true }: PageContainerProps) {
  return (
    <div>
      <Card
        bordered={false}
        style={{ marginBottom: 16 }}
        bodyStyle={{ padding: '16px 24px' }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <div>
            <Title level={4} style={{ margin: 0 }}>
              {title}
            </Title>
            {subtitle && (
              <Text type="secondary" style={{ fontSize: 13 }}>
                {subtitle}
              </Text>
            )}
          </div>
          {extra && (
            <Space wrap>
              {extra}
            </Space>
          )}
        </div>
      </Card>
      <Card bordered={false} bodyStyle={{ padding: bodyPadding ? 24 : 0 }}>
        {children}
      </Card>
    </div>
  );
}

export default PageContainer;
