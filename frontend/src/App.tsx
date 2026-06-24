import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import RequireAuth from './routes';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import NotFound from './pages/NotFound';
import Prefixes from './pages/Prefixes';
import ASNs from './pages/ASNs';
import BGPPeers from './pages/BGPPeers';
import ConsistencyCheck from './pages/Assets/ConsistencyCheck';
import PrefixDetail from './pages/PrefixDetail';
import ASNDetail from './pages/ASNDetail';
import IncidentDetail from './pages/IncidentDetail';
import Rpki from './pages/Rpki';
import Bgp from './pages/Bgp';
import Roas from './pages/Roas';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';

function App() {
  return (
    <Routes>
      {/* 登录页独立路由，不使用主布局 */}
      <Route path="/login" element={<Login />} />

      {/* 主布局路由，包含侧边栏与顶栏，需要登录 */}
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        {/* 资产管理 */}
        <Route path="prefixes" element={<Prefixes />} />
        <Route path="prefixes/:id" element={<PrefixDetail />} />
        <Route path="asns" element={<ASNs />} />
        <Route path="asns/:id" element={<ASNDetail />} />
        <Route path="bgp-peers" element={<BGPPeers />} />
        <Route path="assets/consistency-check" element={<ConsistencyCheck />} />
        {/* RPKI / BGP / ROA 管理 */}
        <Route path="rpki" element={<Rpki />} />
        <Route path="bgp" element={<Bgp />} />
        <Route path="roa" element={<Roas />} />
        {/* 告警事件 */}
        <Route path="alerts" element={<Alerts />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        {/* 系统设置 */}
        <Route path="settings" element={<Settings />} />
      </Route>

      {/* 404 页面 */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default App;
