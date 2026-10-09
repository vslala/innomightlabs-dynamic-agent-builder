import { lazy, Suspense, useEffect, type ComponentType, type ReactElement } from 'react';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { RateLimitBanner } from './components/RateLimitBanner';
import { SiteConcierge } from './components/SiteConcierge';
import { LoadingState } from './components/ui';
import { PUBLIC_PAGES, type PublicPath } from './routes/publicPages';

const basename = import.meta.env.BASE_URL;

const LandingPage = lazyRoute(() => import('./pages/LandingPage'), 'LandingPage');
const Login = lazyRoute(() => import('./pages/Login'), 'Login');
const LoginSuccess = lazyRoute(() => import('./pages/LoginSuccess'), 'LoginSuccess');
const Pricing = lazyRoute(() => import('./pages/Pricing'), 'Pricing');
const PaymentSuccess = lazyRoute(() => import('./pages/PaymentSuccess'), 'PaymentSuccess');
const PaymentCancel = lazyRoute(() => import('./pages/PaymentCancel'), 'PaymentCancel');
const QuickStart = lazyRoute(() => import('./pages/docs/QuickStart'), 'QuickStart');
const AgentToAgent = lazyRoute(() => import('./pages/docs/AgentToAgent'), 'AgentToAgent');
const PublicApi = lazyRoute(() => import('./pages/docs/PublicApi'), 'PublicApi');
const Automations = lazyRoute(() => import('./pages/docs/Automations'), 'Automations');
const WhatsNew = lazyRoute(() => import('./pages/whats-new/WhatsNew'), 'WhatsNew');
const SitemapPage = lazyRoute(() => import('./pages/sitemap/SitemapPage'), 'SitemapPage');
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
const BuildPage = lazyRoute(() => import('./pages/dashboard/build/BuildPage'), 'BuildPage');
const OAuthPopupDone = lazyRoute(() => import('./pages/dashboard/oauth/OAuthPopupDone'), 'OAuthPopupDone');
const BlueprintsPage = lazyRoute(() => import('./pages/dashboard/blueprints/BlueprintsPage'), 'BlueprintsPage');
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
const AgentDreamPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentDreamPage'), 'AgentDreamPage');
const AgentApiKeysPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentApiKeysPage'), 'AgentApiKeysPage');
const AgentKnowledgeBasesPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentKnowledgeBasesPage'), 'AgentKnowledgeBasesPage');
const AgentSkillsPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentSkillsPage'), 'AgentSkillsPage');
const AgentMCPToolsPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentMCPToolsPage'), 'AgentMCPToolsPage');
const AgentA2ATasksPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentA2ATasksPage'), 'AgentA2ATasksPage');
const AgentAnalyticsPage = lazyRoute(() => import('./pages/dashboard/agent-detail/AgentAnalyticsPage'), 'AgentAnalyticsPage');
const AutomationsListPage = lazyRoute(() => import('./pages/dashboard/automations/AutomationsListPage'), 'AutomationsListPage');
const AutomationDetailLayout = lazyRoute(() => import('./pages/dashboard/automations/AutomationDetailLayout'), 'AutomationDetailLayout');
const AutomationWorkspacePage = lazyRoute(() => import('./pages/dashboard/automations/AutomationWorkspacePage'), 'AutomationWorkspacePage');
const WorkspaceRedirect = lazyRoute(() => import('./pages/dashboard/automations/WorkspaceRedirect'), 'WorkspaceRedirect');
const AutomationMarketplacePage = lazyRoute(() => import('./pages/dashboard/automation-marketplace/AutomationMarketplacePage'), 'AutomationMarketplacePage');
const AutomationMarketplaceDetail = lazyRoute(() => import('./pages/dashboard/automation-marketplace/AutomationMarketplaceDetail'), 'AutomationMarketplaceDetail');
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

/** Keyed by every public path, so a page cannot be listed without a component or routed without being listed. */
const publicPageElements: Record<PublicPath, ReactElement> = {
  '/': <LandingPage />,
  '/pricing': <Pricing />,
  '/contact': <Contact />,
  '/downloads': <DownloadsPage />,
  '/downloads/plugins/:pluginId': <PluginDetailsPage />,
  '/docs/quick-start': <QuickStart />,
  '/docs/automations': <Automations />,
  '/docs/agent-to-agent': <AgentToAgent />,
  '/docs/public-api': <PublicApi />,
  '/docs/faq': <FAQ />,
  '/whats-new': <WhatsNew />,
  '/legal/terms': <Terms />,
  '/legal/privacy': <Privacy />,
  '/legal/pricing': <PricingPolicy />,
  '/sitemap': <SitemapPage />,
  '/login': <Login />,
  '/login-success': <LoginSuccess />,
  '/payments/success': <PaymentSuccess />,
  '/payments/cancel': <PaymentCancel />,
};

function App() {
  return (
    <BrowserRouter basename={basename}>
      <ScrollToHash />
      <SiteConcierge />
      <RateLimitBanner />
      <Suspense fallback={<LoadingState />}>
        <Routes>
          {/* Public routes, listed in routes/publicPages.ts */}
          {PUBLIC_PAGES.map((page) => (
            <Route key={page.path} path={page.path} element={publicPageElements[page.path]} />
          ))}

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
            <Route path="dream" element={<AgentDreamPage />} />
            <Route path="api-keys" element={<AgentApiKeysPage />} />
            <Route path="knowledge-bases" element={<AgentKnowledgeBasesPage />} />
            <Route path="skills" element={<AgentSkillsPage />} />
            <Route path="mcp-tools" element={<AgentMCPToolsPage />} />
            <Route path="a2a-tasks" element={<AgentA2ATasksPage />} />
            <Route path="analytics" element={<AgentAnalyticsPage />} />
          </Route>
          <Route path="automations" element={<AutomationsListPage />} />
          <Route path="automations/marketplace" element={<AutomationMarketplacePage />} />
          <Route path="automations/marketplace/:templateId" element={<AutomationMarketplaceDetail />} />
          <Route path="automations/:automationId" element={<AutomationDetailLayout />}>
            <Route index element={<AutomationWorkspacePage />} />
            {/* Triggers, runs, and analytics are panels in the workspace now. */}
            <Route path="triggers" element={<WorkspaceRedirect step="trigger" />} />
            <Route path="runs" element={<WorkspaceRedirect panel="runs" />} />
            <Route path="analytics" element={<WorkspaceRedirect panel="analytics" />} />
          </Route>
          <Route path="conversations" element={<Conversations />} />
          <Route path="conversations/:conversationId" element={<ConversationDetail />} />
          <Route path="artifacts" element={<ArtifactsPage />} />
          <Route path="artifacts/:artifactId" element={<ArtifactOpenPage />} />
          <Route path="build" element={<BuildPage />} />
          <Route path="oauth/done" element={<OAuthPopupDone />} />
          <Route path="blueprints" element={<BlueprintsPage />} />
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
