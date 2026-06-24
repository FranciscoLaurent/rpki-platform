import { message } from 'antd';
import { useAuthStore } from '@/stores/auth';

/** 退出登录工具函数 */
export function logout() {
  useAuthStore.getState().clearAuth();
  message.success('已退出登录');
  window.location.href = '/login';
}

/** 格式化日期时间 */
export function formatDateTime(date: Date | string | number): string {
  const d = new Date(date);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 防抖函数 */
export function debounce<T extends (...args: never[]) => void>(
  fn: T,
  delay: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
