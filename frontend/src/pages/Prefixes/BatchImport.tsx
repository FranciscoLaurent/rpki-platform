// 批量导入前缀
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Input,
  Modal,
  Space,
  Statistic,
  Typography,
  Upload,
  message,
} from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { batchImportPrefixes } from '@/api/prefixes';
import type { PrefixBatchImportResult, PrefixCreate } from '@/api/prefixes';

const { TextArea } = Input;
const { Text } = Typography;

interface BatchImportProps {
  /** 是否显示 */
  open: boolean;
  /** 关闭回调 */
  onClose: () => void;
  /** 导入成功回调 */
  onSuccess?: () => void;
}

/** 示例 JSON */
const SAMPLE_JSON = `[
  {
    "prefix": "192.168.1.0/24",
    "importance": "high",
    "business_service": "核心交易",
    "region": "cn-north",
    "description": "核心交易网段"
  },
  {
    "prefix": "10.0.0.0/16",
    "importance": "medium",
    "business_service": "办公网络",
    "region": "cn-east"
  }
]`;

/** 批量导入前缀组件 */
function BatchImport({ open, onClose, onSuccess }: BatchImportProps) {
  const [jsonText, setJsonText] = useState('');
  const [result, setResult] = useState<PrefixBatchImportResult | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (data: PrefixCreate[]) => batchImportPrefixes({ prefixes: data }),
    onSuccess: (res) => {
      setResult(res);
      if (res.failed === 0) {
        message.success(`成功导入 ${res.success} 条前缀`);
      } else if (res.success > 0) {
        message.warning(`部分导入成功：成功 ${res.success} 条，失败 ${res.failed} 条`);
      } else {
        message.error(`导入失败：${res.failed} 条`);
      }
      queryClient.invalidateQueries({ queryKey: ['prefixes'] });
      queryClient.invalidateQueries({ queryKey: ['prefix-tree'] });
      onSuccess?.();
    },
    onError: () => {
      message.error('批量导入失败');
    },
  });

  /** 解析并提交 */
  const handleSubmit = () => {
    if (!jsonText.trim()) {
      message.warning('请输入 JSON 数据或上传文件');
      return;
    }
    try {
      const parsed = JSON.parse(jsonText);
      if (!Array.isArray(parsed)) {
        message.error('JSON 必须为数组格式');
        return;
      }
      mutation.mutate(parsed as PrefixCreate[]);
    } catch {
      message.error('JSON 格式错误，请检查');
    }
  };

  /** 关闭时重置状态 */
  const handleClose = () => {
    setJsonText('');
    setResult(null);
    mutation.reset();
    onClose();
  };

  /** 上传文件处理 */
  const uploadProps: UploadProps = {
    accept: '.json,application/json',
    maxCount: 1,
    showUploadList: false,
    beforeUpload: (file) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        setJsonText(String(e.target?.result || ''));
        message.success(`已加载文件：${file.name}`);
      };
      reader.onerror = () => message.error('文件读取失败');
      reader.readAsText(file);
      return false; // 阻止自动上传
    },
  };

  return (
    <Modal
      title="批量导入前缀"
      open={open}
      onCancel={handleClose}
      width={720}
      footer={[
        <Button key="cancel" onClick={handleClose}>
          关闭
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={mutation.isPending}
          onClick={handleSubmit}
        >
          开始导入
        </Button>,
      ]}
      destroyOnClose
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="JSON 格式说明"
          description={
            <pre
              style={{
                margin: 0,
                maxHeight: 160,
                overflow: 'auto',
                background: '#f5f5f5',
                padding: 8,
                borderRadius: 4,
                fontSize: 12,
              }}
            >
              {SAMPLE_JSON}
            </pre>
          }
        />

        <Upload.Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽 JSON 文件到此区域上传</p>
          <p className="ant-upload-hint">支持单个 .json 文件，文件内容会被填充到下方文本框</p>
        </Upload.Dragger>

        <div>
          <Text strong>或直接粘贴 JSON 数据：</Text>
          <TextArea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            rows={8}
            placeholder={SAMPLE_JSON}
            style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 12 }}
          />
        </div>

        {result && (
          <div
            style={{
              padding: 16,
              background: '#fafafa',
              borderRadius: 6,
              border: '1px solid #f0f0f0',
            }}
          >
            <Space size="large" wrap>
              <Statistic title="总数" value={result.total} />
              <Statistic title="成功" value={result.success} valueStyle={{ color: '#3f8600' }} />
              <Statistic title="失败" value={result.failed} valueStyle={{ color: '#cf1322' }} />
            </Space>
            {result.errors?.length > 0 && (
              <Alert
                style={{ marginTop: 12 }}
                type="error"
                message="错误详情"
                description={
                  <ul style={{ margin: 0, paddingLeft: 20, maxHeight: 160, overflow: 'auto' }}>
                    {result.errors.map((err, idx) => (
                      <li key={idx} style={{ fontSize: 12 }}>
                        {err}
                      </li>
                    ))}
                  </ul>
                }
              />
            )}
          </div>
        )}
      </Space>
    </Modal>
  );
}

export default BatchImport;
