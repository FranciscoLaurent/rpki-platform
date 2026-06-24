// BGP 邻居创建/编辑表单
import { useEffect } from 'react';
import { Form, Input, InputNumber, Modal, Select, message } from 'antd';
import type { BGPPeer } from '@/api/bgp-peers';
import { createBGPPeer, updateBGPPeer } from '@/api/bgp-peers';

const { TextArea } = Input;

interface BGPPeerFormProps {
  /** 是否显示 */
  open: boolean;
  /** 编辑时的初始数据，为空表示新建 */
  peer?: BGPPeer | null;
  /** 关闭回调 */
  onClose: () => void;
  /** 提交成功回调 */
  onSuccess?: () => void;
}

/** 地址族选项 */
const FAMILY_OPTIONS = [
  { value: 4, label: 'IPv4' },
  { value: 6, label: 'IPv6' },
];

/** 会话类型选项 */
const SESSION_TYPE_OPTIONS = [
  { value: 'ebgp', label: 'eBGP（外部 BGP）' },
  { value: 'ibgp', label: 'iBGP（内部 BGP）' },
  { value: 'rr-client', label: 'RR Client（路由反射客户端）' },
  { value: 'rs-client', label: 'RS Client（路由服务器客户端）' },
];

/** IPv4 校验 */
function isValidIPv4(ip: string): boolean {
  const parts = ip.split('.');
  if (parts.length !== 4) return false;
  return parts.every((p) => {
    const n = Number(p);
    return Number.isInteger(n) && n >= 0 && n <= 255 && String(n) === p;
  });
}

/** IPv6 校验（简化版） */
function isValidIPv6(ip: string): boolean {
  if (!ip) return false;
  // 包含至少一个冒号，且仅含合法字符
  if (!ip.includes(':')) return false;
  if (!/^[0-9a-fA-F:]+$/.test(ip)) return false;
  // 不允许多于 7 个冒号（:: 计为 1 个分隔）
  const colons = (ip.match(/:/g) || []).length;
  if (colons > 7 && !ip.includes('::')) return false;
  // 简化校验：尝试构造 URL 解析
  try {
    // eslint-disable-next-line no-new
    new URL(`http://[${ip}]`);
    return true;
  } catch {
    return false;
  }
}

/** IP 地址校验 */
function validateIP(_: unknown, value: string): Promise<void> {
  if (!value) {
    return Promise.reject(new Error('请输入 Peer IP 地址'));
  }
  if (isValidIPv4(value) || isValidIPv6(value)) {
    return Promise.resolve();
  }
  return Promise.reject(new Error('IP 地址格式不正确'));
}

/** ASN 范围校验 */
function validateASN(_: unknown, value: number): Promise<void> {
  if (value === undefined || value === null) {
    return Promise.reject(new Error('请输入 Remote ASN'));
  }
  if (!Number.isInteger(value)) {
    return Promise.reject(new Error('ASN 必须为整数'));
  }
  if (value < 1 || value > 4294967295) {
    return Promise.reject(new Error('ASN 范围必须在 1 - 4294967295 之间'));
  }
  return Promise.resolve();
}

/** BGP 邻居创建/编辑表单组件 */
function BGPPeerForm({ open, peer, onClose, onSuccess }: BGPPeerFormProps) {
  const [form] = Form.useForm();
  const isEdit = !!peer;

  useEffect(() => {
    if (open) {
      if (peer) {
        form.setFieldsValue({
          peer_ip: peer.peer_ip,
          remote_asn: peer.remote_asn,
          address_family: peer.address_family,
          session_type: peer.session_type,
          route_policy: peer.route_policy,
          max_prefixes: peer.max_prefixes,
          description: peer.description,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          address_family: 4,
          session_type: 'ebgp',
          max_prefixes: 1000,
        });
      }
    }
  }, [open, peer, form]);

  /** 提交表单 */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit && peer) {
        await updateBGPPeer(peer.id, values);
        message.success('BGP 邻居更新成功');
      } else {
        await createBGPPeer(values);
        message.success('BGP 邻居创建成功');
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
      title={isEdit ? '编辑 BGP 邻居' : '新建 BGP 邻居'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      width={600}
      destroyOnClose
      maskClosable={false}
      okText="保存"
      cancelText="取消"
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="peer_ip"
          label="Peer IP"
          rules={[{ required: true, validator: validateIP }]}
          tooltip="对端 BGP 邻居 IP 地址"
        >
          <Input placeholder="例如 192.168.1.1 或 2001:db8::1" />
        </Form.Item>

        <Form.Item
          name="remote_asn"
          label="Remote ASN"
          rules={[{ required: true, validator: validateASN }]}
          tooltip="范围：1 - 4294967295"
        >
          <InputNumber
            min={1}
            max={4294967295}
            precision={0}
            style={{ width: '100%' }}
            placeholder="例如 64512"
          />
        </Form.Item>

        <Form.Item name="address_family" label="地址族" rules={[{ required: true }]}>
          <Select options={FAMILY_OPTIONS} placeholder="请选择地址族" />
        </Form.Item>

        <Form.Item name="session_type" label="会话类型" rules={[{ required: true }]}>
          <Select options={SESSION_TYPE_OPTIONS} placeholder="请选择会话类型" />
        </Form.Item>

        <Form.Item
          name="max_prefixes"
          label="最大前缀数"
          rules={[
            { required: true, message: '请输入最大前缀数' },
            {
              validator: (_, v) =>
                v !== undefined && v !== null && Number.isInteger(v) && v > 0
                  ? Promise.resolve()
                  : Promise.reject(new Error('必须为正整数')),
            },
          ]}
          tooltip="超过该阈值会触发告警或会话中断"
        >
          <InputNumber min={1} precision={0} style={{ width: '100%' }} placeholder="例如 1000" />
        </Form.Item>

        <Form.Item name="route_policy" label="路由策略">
          <Input placeholder="例如：import-all-export-filtered" />
        </Form.Item>

        <Form.Item name="description" label="描述">
          <TextArea rows={3} placeholder="BGP 邻居用途说明" maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default BGPPeerForm;
