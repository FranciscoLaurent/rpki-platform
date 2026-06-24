import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';

/** 路由守卫：保护需要登录才能访问的路由 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((state) => state.token);
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

export default RequireAuth;
