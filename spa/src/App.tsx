import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { LandingPage } from './pages/LandingPage';
import { LoginSuccess } from './pages/LoginSuccess';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { Overview } from './pages/dashboard/Overview';
import { AgentsList } from './pages/dashboard/AgentsList';
import { AgentDetail } from './pages/dashboard/AgentDetail';
import { Conversations } from './pages/dashboard/Conversations';
import { Settings } from './pages/dashboard/Settings';

const basename = import.meta.env.BASE_URL;

function App() {
  return (
    <BrowserRouter basename={basename}>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login-success" element={<LoginSuccess />} />

        {/* Protected dashboard routes */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Overview />} />
          <Route path="agents" element={<AgentsList />} />
          <Route path="agents/:id" element={<AgentDetail />} />
          <Route path="conversations" element={<Conversations />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
