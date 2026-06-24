// 通用搜索栏组件：支持搜索框 + 过滤下拉
import type { ReactNode } from 'react';
import { Input, Space } from 'antd';
import type { InputProps } from 'antd';

const { Search } = Input;

export interface FilterOption {
  /** 唯一标识 */
  key: string;
  /** 过滤器节点（通常是 Select） */
  node: ReactNode;
}

interface SearchBarProps {
  /** 搜索关键字占位符 */
  placeholder?: string;
  /** 搜索框值 */
  value?: string;
  /** 搜索值变化回调 */
  onChange?: (value: string) => void;
  /** 点击搜索/回车回调 */
  onSearch?: (value: string) => void;
  /** 过滤器选项列表 */
  filters?: FilterOption[];
  /** 右侧额外操作区 */
  extra?: ReactNode;
  /** 搜索框宽度 */
  searchWidth?: number | string;
  /** 搜索框属性透传 */
  inputProps?: Partial<InputProps>;
  /** 是否允许清除 */
  allowClear?: boolean;
}

/** 通用搜索栏：左侧搜索框 + 过滤下拉，右侧额外操作 */
function SearchBar({
  placeholder = '请输入关键字搜索',
  value,
  onChange,
  onSearch,
  filters = [],
  extra,
  searchWidth = 240,
  inputProps,
  allowClear = true,
}: SearchBarProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 12,
        marginBottom: 16,
      }}
    >
      <Space wrap>
        <Search
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
          onSearch={(v) => onSearch?.(v)}
          allowClear={allowClear}
          style={{ width: searchWidth }}
          {...inputProps}
        />
        {filters.map((f) => (
          <span key={f.key}>{f.node}</span>
        ))}
      </Space>
      {extra && <Space wrap>{extra}</Space>}
    </div>
  );
}

export default SearchBar;
