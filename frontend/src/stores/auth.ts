import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  /** 访问令牌 */
  token: string | null;
  /** 用户名 */
  username: string | null;
  /** 设置认证信息 */
  setAuth: (token: string, username: string) => void;
  /** 清除认证信息（登出） */
  clearAuth: () => void;
}

/** 认证状态管理（基于 zustand + persist 持久化） */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      setAuth: (token: string, username: string) => set({ token, username }),
      clearAuth: () => set({ token: null, username: null }),
    }),
    {
      name: 'rpki-auth-storage',
      partialize: (state) => ({ token: state.token, username: state.username }),
    },
  ),
);
