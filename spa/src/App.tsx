import { useEffect } from 'react';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { LandingPage } from './pages/LandingPage';
import { Login } from './pages/Login';
import { LoginSuccess } from './pages/LoginSuccess';
import { Pricing } from './pages/Pricing';
import { PaymentSuccess } from './pages/PaymentSuccess';
import { PaymentCancel } from './pages/PaymentCancel';
import { QuickStart } from './pages/docs/QuickStart';
import { FAQ } from './pages/docs/FAQ';
import { Terms } from './pages/legal/Terms';
import { PricingPolicy } from './pages/legal/PricingPolicy';
import { Privacy } from './pages/legal/Privacy';
import { Contact } from './pages/Contact';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { RateLimitBanner } from './components/RateLimitBanner';
import BetaBanner from './components/BetaBanner';
import { Overview } from './pages/dashboard/Overview';
import { AgentsList } from './pages/dashboard/AgentsList';
import { AgentCreate } from './pages/dashboard/AgentCreate';
import { Conversations } from './pages/dashboard/Conversations';
import { ConversationDetail } from './pages/dashboard/ConversationDetail';
import { KnowledgeBases } from './pages/dashboard/KnowledgeBases';
import { KnowledgeBaseDetail } from './pages/dashboard/KnowledgeBaseDetail';
import { Settings } from './pages/dashboard/Settings';
import { AgentDetailLayout } from './pages/dashboard/agent-detail/AgentDetailLayout';
import { AgentOverviewPage } from './pages/dashboard/agent-detail/AgentOverviewPage';
import { AgentMemoryPage } from './pages/dashboard/agent-detail/AgentMemoryPage';
import { AgentApiKeysPage } from './pages/dashboard/agent-detail/AgentApiKeysPage';
import { AgentKnowledgeBasesPage } from './pages/dashboard/agent-detail/AgentKnowledgeBasesPage';
import { AgentSkillsPage } from './pages/dashboard/agent-detail/AgentSkillsPage';
import { AgentAnalyticsPage } from './pages/dashboard/agent-detail/AgentAnalyticsPage';

const basename = import.meta.env.BASE_URL;

function ScrollToHash() {
  const location = useLocation();

  useEffect(() => {
    if (!location.hash) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    const id = location.hash.replace('#', '');
    const target = document.getElementById(id);
    if (!target) {
      return;
    }
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [location]);

  return null;
}

function App() {
  return (
    <BrowserRouter basename={basename}>
      <ScrollToHash />
      <BetaBanner />
      <RateLimitBanner />
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/payments/success" element={<PaymentSuccess />} />
        <Route path="/payments/cancel" element={<PaymentCancel />} />
        <Route path="/login-success" element={<LoginSuccess />} />
        <Route path="/docs/quick-start" element={<QuickStart />} />
        <Route path="/docs/faq" element={<FAQ />} />
        <Route path="/legal/terms" element={<Terms />} />
        <Route path="/legal/privacy" element={<Privacy />} />
        <Route path="/legal/pricing" element={<PricingPolicy />} />
        <Route path="/contact" element={<Contact />} />

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
          <Route path="agents/:agentId" element={<AgentDetailLayout />}>
            <Route index element={<AgentOverviewPage />} />
            <Route path="memory" element={<AgentMemoryPage />} />
            <Route path="api-keys" element={<AgentApiKeysPage />} />
            <Route path="knowledge-bases" element={<AgentKnowledgeBasesPage />} />
            <Route path="skills" element={<AgentSkillsPage />} />
            <Route path="analytics" element={<AgentAnalyticsPage />} />
          </Route>
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
