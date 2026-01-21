import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { LandingPage } from './pages/LandingPage';
import { LoginSuccess } from './pages/LoginSuccess';
import { Pricing } from './pages/Pricing';
import { PaymentSuccess } from './pages/PaymentSuccess';
import { PaymentCancel } from './pages/PaymentCancel';
import { QuickStart } from './pages/docs/QuickStart';
import { FAQ } from './pages/docs/FAQ';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { RateLimitBanner } from './components/RateLimitBanner';
import { Overview } from './pages/dashboard/Overview';
import { AgentsList } from './pages/dashboard/AgentsList';
import { AgentCreate } from './pages/dashboard/AgentCreate';
import { AgentDetail } from './pages/dashboard/AgentDetail';
import { Conversations } from './pages/dashboard/Conversations';
import { ConversationDetail } from './pages/dashboard/ConversationDetail';
import { KnowledgeBases } from './pages/dashboard/KnowledgeBases';
import { KnowledgeBaseDetail } from './pages/dashboard/KnowledgeBaseDetail';
import { Settings } from './pages/dashboard/Settings';

const basename = import.meta.env.BASE_URL;

function App() {
  return (
    <BrowserRouter basename={basename}>
      <RateLimitBanner />
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/payments/success" element={<PaymentSuccess />} />
        <Route path="/payments/cancel" element={<PaymentCancel />} />
        <Route path="/login-success" element={<LoginSuccess />} />
        <Route path="/docs/quick-start" element={<QuickStart />} />
        <Route path="/docs/faq" element={<FAQ />} />

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
          <Route path="agents/new" element={<AgentCreate />} />
          <Route path="agents/:agentId" element={<AgentDetail />} />
          <Route path="conversations" element={<Conversations />} />
          <Route path="conversations/:conversationId" element={<ConversationDetail />} />
          <Route path="knowledge-bases" element={<KnowledgeBases />} />
          <Route path="knowledge-bases/:kbId" element={<KnowledgeBaseDetail />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
