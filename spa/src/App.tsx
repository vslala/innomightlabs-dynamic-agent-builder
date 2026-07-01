import { lazy, Suspense, useEffect, type ComponentType } from 'react';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { RateLimitBanner } from './components/RateLimitBanner';
import BetaBanner from './components/BetaBanner';
import { LoadingState } from './components/ui';

const basename = import.meta.env.BASE_URL;

const LandingPage = lazyRoute(() => import('./pages/LandingPage'), 'LandingPage');
const Login = lazyRoute(() => import('./pages/Login'), 'Login');
const LoginSuccess = lazyRoute(() => import('./pages/LoginSuccess'), 'LoginSuccess');
const Pricing = lazyRoute(() => import('./pages/Pricing'), 'Pricing');
const PaymentSuccess = lazyRoute(() => import('./pages/PaymentSuccess'), 'PaymentSuccess');
const PaymentCancel = lazyRoute(() => import('./pages/PaymentCancel'), 'PaymentCancel');
const QuickStart = lazyRoute(() => import('./pages/docs/QuickStart'), 'QuickStart');
const FAQ = lazyRoute(() => import('./pages/docs/FAQ'), 'FAQ');
const Terms = lazyRoute(() => import('./pages/legal/Terms'), 'Terms');
const PricingPolicy = lazyRoute(() => import('./pages/legal/PricingPolicy'), 'PricingPolicy');
const Privacy = lazyRoute(() => import('./pages/legal/Privacy'), 'Privacy');
const Contact = lazyRoute(() => import('./pages/Contact'), 'Contact');
const DownloadsPage = lazyRoute(() => import('./pages/DownloadsPage'), 'DownloadsPage');
const PluginDetailsPage = lazyRoute(() => import('./pages/PluginDetailsPage'), 'PluginDetailsPage');
const Overview = lazyRoute(() => import('./pages/dashboard/Overview'), 'Overview');
const AgentsList = lazyRoute(() => import('./pages/dashboard/AgentsList'), 'AgentsList');
const AgentCreate = lazyRoute(() => import('./pages/dashboard/AgentCreate'), 'AgentCreate');
const AgentMarketplacePage = lazyRoute(() => import('./pages/dashboard/agent-marketplace/AgentMarketplacePage'), 'AgentMarketplacePage');
const MarketplaceAgentDetail = lazyRoute(() => import('./pages/dashboard/agent-marketplace/MarketplaceAgentDetail'), 'MarketplaceAgentDetail');
const Conversations = lazyRoute(() => import('./pages/dashboard/Conversations'), 'Conversations');
const ConversationDetail = lazyRoute(() => import('./pages/dashboard/ConversationDetail'), 'ConversationDetail');
const ArtifactsPage = lazyRoute(() => import('./pages/dashboard/ArtifactsPage'), 'ArtifactsPage');
const ArtifactOpenPage = lazyRoute(() => import('./pages/dashboard/ArtifactOpenPage'), 'ArtifactOpenPage');
const KnowledgeBases = lazyRoute(() => import('./pages/dashboard/KnowledgeBases'), 'KnowledgeBases');
const KnowledgeBaseDetail = lazyRoute(() => import('./pages/dashboard/KnowledgeBaseDetail'), 'KnowledgeBaseDetail');
const Settings = lazyRoute(() => import('./pages/dashboard/Settings'), 'Settings');
const ConnectorsPage = lazyRoute(() => import('./pages/dashboard/ConnectorsPage'), 'ConnectorsPage');
const AgentDetailLayout = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentDetailLayout'), 'AgentDetailLayout');
const AgentOverviewPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentOverviewPage'), 'AgentOverviewPage');
const AgentMemoryPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentMemoryPage'), 'AgentMemoryPage');
const AgentApiKeysPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentApiKeysPage'), 'AgentApiKeysPage');
const AgentKnowledgeBasesPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentKnowledgeBasesPage'), 'AgentKnowledgeBasesPage');
const AgentSkillsPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentSkillsPage'), 'AgentSkillsPage');
const AgentMCPToolsPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentMCPToolsPage'), 'AgentMCPToolsPage');
const AgentAnalyticsPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentAnalyticsPage'), 'AgentAnalyticsPage');
const AutomationsListPage = lazyRoute(() => import('./pages/dashboard/automations/AutomationsListPage'), 'AutomationsListPage');
const AutomationDetailLayout = lazyRoute(() => import('./pages/dashboard/automations/AutomationDetailLayout'), 'AutomationDetailLayout');
const AutomationBuilderPage = lazyRoute(() => import('./pages/dashboard/automations/AutomationBuilderPage'), 'AutomationBuilderPage');
const AutomationRunsPage = lazyRoute(() => import('./pages/dashboard/automations/AutomationRunsPage'), 'AutomationRunsPage');
const AutomationAnalyticsPage = lazyRoute(() => import('./pages/dashboard/automations/AutomationAnalyticsPage'), 'AutomationAnalyticsPage');
const AutomationTriggersPage = lazyRoute(() => import('./pages/dashboard/automations/AutomationTriggersPage'), 'AutomationTriggersPage');
const WhatsNewPage = lazyRoute(() => import('./pages/dashboard/WhatsNewPage'), 'WhatsNewPage');

function lazyRoute<T extends Record<string, ComponentType>>(
  loader: () => Promise<T>,
  exportName: keyof T
) {
  return lazy(async () => {
    const module = await loader();
    return { default: module[exportName] };
  });
}

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
      <Suspense fallback={<LoadingState />}>
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
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/downloads/plugins/:pluginId" element={<PluginDetailsPage />} />

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
          <Route path="agents/marketplace" element={<AgentMarketplacePage />} />
          <Route path="agents/marketplace/:templateId" element={<MarketplaceAgentDetail />} />
          <Route path="agents/:agentId" element={<AgentDetailLayout />}>
            <Route index element={<AgentOverviewPage />} />
            <Route path="memory" element={<AgentMemoryPage />} />
            <Route path="api-keys" element={<AgentApiKeysPage />} />
            <Route path="knowledge-bases" element={<AgentKnowledgeBasesPage />} />
            <Route path="skills" element={<AgentSkillsPage />} />
            <Route path="mcp-tools" element={<AgentMCPToolsPage />} />
            <Route path="analytics" element={<AgentAnalyticsPage />} />
          </Route>
          <Route path="automations" element={<AutomationsListPage />} />
          <Route path="automations/:automationId" element={<AutomationDetailLayout />}>
            <Route index element={<AutomationBuilderPage />} />
            <Route path="triggers" element={<AutomationTriggersPage />} />
            <Route path="runs" element={<AutomationRunsPage />} />
            <Route path="analytics" element={<AutomationAnalyticsPage />} />
          </Route>
          <Route path="conversations" element={<Conversations />} />
          <Route path="conversations/:conversationId" element={<ConversationDetail />} />
          <Route path="artifacts" element={<ArtifactsPage />} />
          <Route path="artifacts/:artifactId" element={<ArtifactOpenPage />} />
          <Route path="knowledge-bases" element={<KnowledgeBases />} />
          <Route path="knowledge-bases/:kbId" element={<KnowledgeBaseDetail />} />
          <Route path="connectors" element={<ConnectorsPage />} />
          <Route path="whats-new" element={<WhatsNewPage />} />
          <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
