import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AuthPage from './pages/AuthPage';
import { clearSession, isAuthenticated, refreshToken } from './lib/auth';
import LandingPage from './pages/LandingPage';
import ProductPage from './pages/ProductPage';

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
  return authenticated ? <>{children}</> : <Navigate to="/login" replace />;
}
import DashboardPage from './pages/DashboardPage';

export default function App() {
  const [, setSessionVersion] = useState(0);

  useEffect(() => {
    void refreshToken().catch(clearSession).finally(() => setSessionVersion(version => version + 1));
  }, []);

  return <BrowserRouter><Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={<AuthPage signup={false} />} />
    <Route path="/signup" element={<AuthPage signup />} />
    <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
    <Route path="/:slug" element={<ProductPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter>;
}
