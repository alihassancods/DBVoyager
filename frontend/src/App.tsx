import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AuthPage from './pages/AuthPage';
import { clearSession, isAuthenticated, refreshToken } from './lib/auth';
import LandingPage from './pages/LandingPage';
import ProductPage from './pages/ProductPage';
import ConnectionsPage from './pages/ConnectionsPage';
import QueryDetailsPage from './pages/QueryDetailsPage';
import OptimizerPage from './pages/OptimizerPage';
import SchemaExplorerPage from './pages/SchemaExplorerPage';
import HealthChecksPage from './pages/HealthChecksPage';
import BiChatPage from './pages/BiChatPage';
import KpisPage from './pages/KpisPage';
import AppShell from './AppShell';
import { ToastProvider } from './components/ui';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(isAuthenticated());

  useEffect(() => {
    void refreshToken().then(() => setAuthenticated(true)).catch(() => {
      clearSession();
      setAuthenticated(false);
    }).finally(() => setChecking(false));
  }, []);

  if (checking) return <main className="grid min-h-screen place-items-center bg-voyager-navy text-sm text-voyager-text-secondary">Checking your session…</main>;
  return authenticated ? <AppShell>{children}</AppShell> : <Navigate to="/login" replace />;
}

function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  useEffect(() => { void refreshToken().then(() => setAuthenticated(true)).catch(() => { clearSession(); setAuthenticated(false); }).finally(() => setChecking(false)); }, []);
  if (checking) return <main className="grid min-h-screen place-items-center bg-voyager-navy text-sm text-voyager-text-secondary">Checking your session…</main>;
  return authenticated ? <Navigate to="/dashboard" replace /> : <>{children}</>;
}
import DashboardPage from './pages/DashboardPage';

export default function App() {
  return <ToastProvider><BrowserRouter><Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<PublicOnlyRoute><AuthPage signup={false} /></PublicOnlyRoute>} />
    <Route path="/signup" element={<PublicOnlyRoute><AuthPage signup /></PublicOnlyRoute>} />
    <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
    <Route path="/connections" element={<ProtectedRoute><ConnectionsPage /></ProtectedRoute>} />
    <Route path="/optimizer" element={<ProtectedRoute><OptimizerPage /></ProtectedRoute>} />
    <Route path="/schema-explorer" element={<ProtectedRoute><SchemaExplorerPage /></ProtectedRoute>} />
    <Route path="/health-checks" element={<ProtectedRoute><HealthChecksPage /></ProtectedRoute>} />
    <Route path="/bi-chat" element={<ProtectedRoute><BiChatPage /></ProtectedRoute>} />
    <Route path="/kpis" element={<ProtectedRoute><KpisPage /></ProtectedRoute>} />
    <Route path="/connections/:connectionId/optimizer/queries/:queryId" element={<ProtectedRoute><QueryDetailsPage /></ProtectedRoute>} />
    <Route path="/:slug" element={<ProductPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter></ToastProvider>;
}
