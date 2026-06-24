// ASN 创建/编辑表单
import { useEffect } from 'react';
import { Form, Input, InputNumber, Modal, Select, message } from 'antd';
import type { ASN } from '@/api/asns';
import { createASN, updateASN } from '@/api/asns';

const { TextArea } = Input;

interface ASNFormProps {
  /** 是否显示 */
  open: boolean;
  /** 编辑时的初始数据，为空表示新建 */
  asn?: ASN | null;
  /** 关闭回调 */
  onClose: () => void;
  /** 提交成功回调 */
  onSuccess?: () => void;
}

/** ASN 类型选项 */
const TYPE_OPTIONS = [
  { value: 'transit', label: ' transit（上游运营商）' },
  { value: 'customer', label: 'customer（客户）' },
  { value: 'peer', label: 'peer（对等互联）' },
  { value: 'internal', label: 'internal（内部）' },
];

/** 状态选项 */
const STATUS_OPTIONS = [
  { value: 'active', label: '活跃' },
  { value: 'suspended', label: '暂停' },
  { value: 'deprecated', label: '废弃' },
];

/** 风险画像选项 */
const RISK_OPTIONS = [
  { value: 'low', label: '低风险' },
  { value: 'medium', label: '中风险' },
  { value: 'high', label: '高风险' },
  { value: 'critical', label: '极高风险' },
];

/** ASN 范围校验：1 - 4294967295 */
function validateASN(_: unknown, value: number): Promise<void> {
  if (value === undefined || value === null) {
    return Promise.reject(new Error('请输入 ASN 号'));
  }
  if (!Number.isInteger(value)) {
    return Promise.reject(new Error('ASN 必须为整数'));
  }
  if (value < 1 || value > 4294967295) {
    return Promise.reject(new Error('ASN 范围必须在 1 - 4294967295 之间'));
  }
  return Promise.resolve();
}

/** 邮箱校验 */
function validateEmail(_: unknown, value: string): Promise<void> {
  if (!value) return Promise.resolve();
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (re.test(value)) return Promise.resolve();
  return Promise.reject(new Error('邮箱格式不正确'));
}

/** ASN 创建/编辑表单组件 */
function ASNForm({ open, asn, onClose, onSuccess }: ASNFormProps) {
  const [form] = Form.useForm();
  const isEdit = !!asn;

  useEffect(() => {
    if (open) {
      if (asn) {
        form.setFieldsValue({
          asn: asn.asn,
          name: asn.name,
          type: asn.type,
          status: asn.status,
          contact: asn.contact,
          email: asn.email,
          noc_phone: asn.noc_phone,
          emergency_contact: asn.emergency_contact,
          relationship_tags: asn.relationship_tags,
          risk_profile: asn.risk_profile,
          description: asn.description,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({ type: 'customer', status: 'active', risk_profile: 'low' });
      }
    }
  }, [open, asn, form]);

  /** 提交表单 */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit && asn) {
        await updateASN(asn.id, values);
        message.success('ASN 更新成功');
      } else {
        await createASN(values);
        message.success('ASN 创建成功');
      }
      onSuccess?.();
      onClose();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return;
      }
    }
  };

  return (
    <Modal
      title={isEdit ? '编辑 ASN' : '新建 ASN'}
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
          name="asn"
          label="ASN 号"
          rules={[{ required: true, validator: validateASN }]}
          tooltip="范围：1 - 4294967295"
        >
          <InputNumber
            min={1}
            max={4294967295}
            precision={0}
            style={{ width: '100%' }}
            placeholder="例如 64512"
            disabled={isEdit}
          />
        </Form.Item>

        <Form.Item
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入名称' },
            { max: 200, message: '名称不超过 200 字符' },
          ]}
        >
          <Input placeholder="例如：Acme Telecom" />
        </Form.Item>

        <Form.Item name="type" label="类型" rules={[{ required: true }]}>
          <Select options={TYPE_OPTIONS} placeholder="请选择类型" />
        </Form.Item>

        <Form.Item name="status" label="状态" rules={[{ required: true }]}>
          <Select options={STATUS_OPTIONS} placeholder="请选择状态" />
        </Form.Item>

        <Form.Item name="risk_profile" label="风险画像" rules={[{ required: true }]}>
          <Select options={RISK_OPTIONS} placeholder="请选择风险画像" />
        </Form.Item>

        <Form.Item name="contact" label="联系人">
          <Input placeholder="联系人姓名" />
        </Form.Item>

        <Form.Item name="email" label="邮箱" rules={[{ validator: validateEmail }]}>
          <Input placeholder="contact@example.com" />
        </Form.Item>

        <Form.Item name="noc_phone" label="NOC 电话">
          <Input placeholder="+86-10-xxxxxxxx" />
        </Form.Item>

        <Form.Item name="emergency_contact" label="应急联系">
          <Input placeholder="7x24 应急联系方式" />
        </Form.Item>

        <Form.Item name="relationship_tags" label="关系标签">
          <Select
            mode="tags"
            placeholder="输入后回车添加关系标签"
            tokenSeparators={[',']}
          />
        </Form.Item>

        <Form.Item name="description" label="描述">
          <TextArea rows={3} placeholder="ASN 用途说明" maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default ASNForm;
