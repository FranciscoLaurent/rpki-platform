// 前缀创建/编辑表单
import { useEffect } from 'react';
import { Form, Input, Modal, Select, message } from 'antd';
import type { Prefix } from '@/api/prefixes';
import { createPrefix, updatePrefix } from '@/api/prefixes';

const { TextArea } = Input;

interface PrefixFormProps {
  /** 是否显示 */
  open: boolean;
  /** 编辑时的初始数据，为空表示新建 */
  prefix?: Prefix | null;
  /** 关闭回调 */
  onClose: () => void;
  /** 提交成功回调 */
  onSuccess?: () => void;
}

/** 重要性选项 */
const IMPORTANCE_OPTIONS = [
  { value: 'critical', label: '关键' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
];

/** 状态选项 */
const STATUS_OPTIONS = [
  { value: 'active', label: '活跃' },
  { value: 'reserved', label: '保留' },
  { value: 'deprecated', label: '废弃' },
  { value: 'conflict', label: '冲突' },
];

/** 常用地域选项 */
const REGION_OPTIONS = [
  { value: 'cn-north', label: '华北' },
  { value: 'cn-east', label: '华东' },
  { value: 'cn-south', label: '华南' },
  { value: 'cn-southwest', label: '西南' },
  { value: 'cn-northwest', label: '西北' },
  { value: 'overseas', label: '海外' },
];

/** CIDR 格式校验 */
function validateCIDR(_: unknown, value: string): Promise<void> {
  if (!value) {
    return Promise.reject(new Error('请输入 CIDR 格式的前缀'));
  }
  // IPv4/IPv6 CIDR 校验
  const v4 = /^(\d{1,3}\.){3}\d{1,3}\/(3[0-2]|[12]?\d)$/;
  const v6 = /^([0-9a-fA-F:]+)\/(12[0-8]|1[01]\d|[1-9]?\d)$/;
  if (v4.test(value) || v6.test(value)) {
    // 进一步校验 IPv4 各段范围
    if (v4.test(value)) {
      const parts = value.split('/')[0].split('.');
      const valid = parts.every((p) => Number(p) >= 0 && Number(p) <= 255);
      if (!valid) {
        return Promise.reject(new Error('IPv4 地址各段必须在 0-255 之间'));
      }
    }
    return Promise.resolve();
  }
  return Promise.reject(new Error('CIDR 格式不正确，例如 192.168.1.0/24 或 2001:db8::/32'));
}

/** 前缀创建/编辑表单组件 */
function PrefixForm({ open, prefix, onClose, onSuccess }: PrefixFormProps) {
  const [form] = Form.useForm();
  const isEdit = !!prefix;

  useEffect(() => {
    if (open) {
      if (prefix) {
        form.setFieldsValue({
          prefix: prefix.prefix,
          importance: prefix.importance,
          business_service: prefix.business_service,
          region: prefix.region,
          site: prefix.site,
          cloud_zone: prefix.cloud_zone,
          tags: prefix.tags,
          description: prefix.description,
          status: prefix.status,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({ importance: 'medium', status: 'active' });
      }
    }
  }, [open, prefix, form]);

  /** 提交表单 */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit && prefix) {
        await updatePrefix(prefix.id, values);
        message.success('前缀更新成功');
      } else {
        await createPrefix(values);
        message.success('前缀创建成功');
      }
      onSuccess?.();
      onClose();
    } catch (err) {
      // 校验错误或 API 错误，API 错误已由拦截器统一提示
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return;
      }
    }
  };

  return (
    <Modal
      title={isEdit ? '编辑前缀' : '新建前缀'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      width={640}
      destroyOnClose
      maskClosable={false}
      okText="保存"
      cancelText="取消"
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="prefix"
          label="前缀 (CIDR)"
          rules={[{ required: true, validator: validateCIDR }]}
          tooltip="例如 192.168.1.0/24 或 2001:db8::/32"
        >
          <Input placeholder="192.168.1.0/24" disabled={isEdit} />
        </Form.Item>

        <Form.Item name="importance" label="重要性" rules={[{ required: true }]}>
          <Select options={IMPORTANCE_OPTIONS} placeholder="请选择重要性" />
        </Form.Item>

        <Form.Item name="status" label="状态" rules={[{ required: true }]}>
          <Select options={STATUS_OPTIONS} placeholder="请选择状态" />
        </Form.Item>

        <Form.Item name="business_service" label="业务归属">
          <Input placeholder="例如：核心交易系统" />
        </Form.Item>

        <Form.Item name="region" label="地域">
          <Select options={REGION_OPTIONS} placeholder="请选择地域" allowClear />
        </Form.Item>

        <Form.Item name="site" label="机房">
          <Input placeholder="例如：北京-1" />
        </Form.Item>

        <Form.Item name="cloud_zone" label="云区域">
          <Input placeholder="例如：cn-north-1a" />
        </Form.Item>

        <Form.Item name="tags" label="标签">
          <Select
            mode="tags"
            placeholder="输入后回车添加标签"
            tokenSeparators={[',']}
          />
        </Form.Item>

        <Form.Item name="description" label="描述">
          <TextArea rows={3} placeholder="前缀用途说明" maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default PrefixForm;
