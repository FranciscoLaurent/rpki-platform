import axios, { AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';
import { useAuthStore } from '@/stores/auth';

/** 创建 axios 实例 */
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/** 请求拦截器：自动添加 Authorization 头 */
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().token;
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  },
);

/** 响应拦截器：统一处理错误与 401 跳转 */
client.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError<{ detail?: unknown }>) => {
    if (error.response) {
      const { status, data } = error.response;

      if (status === 401) {
        // 401 未授权：清除认证信息并跳转登录页
        useAuthStore.getState().clearAuth();
        message.error('登录已过期，请重新登录');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      // detail 可能是字符串（普通错误）或数组（FastAPI 422 验证错误）
      let errorMsg: string;
      if (typeof data?.detail === 'string') {
        errorMsg = data.detail;
      } else if (Array.isArray(data?.detail)) {
        errorMsg = data.detail
          .map((e: { msg?: string }) => e?.msg ?? JSON.stringify(e))
          .join('; ');
      } else {
        errorMsg = `请求失败 (${status})`;
      }
      message.error(errorMsg);
    } else if (error.request) {
      message.error('网络异常，请检查网络连接');
    } else {
      message.error('请求配置错误');
    }
    return Promise.reject(error);
  },
);

/** 封装 GET 请求 */
export function get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return client.get(url, config);
}

/** 封装 POST 请求 */
export function post<T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  return client.post(url, data, config);
}

/** 封装 PUT 请求 */
export function put<T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  return client.put(url, data, config);
}

/** 封装 DELETE 请求 */
export function del<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return client.delete(url, config);
}

export default client;
