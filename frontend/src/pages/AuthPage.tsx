import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import officialLogo from '../../../../sample/stitch/stitch_dbvoyager_platform_ui/dbvoyager_logo_icon/screen.png';
import { authenticate } from '../lib/auth';

export default function AuthPage({ signup }: { signup: boolean }) {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const password = String(values.get('password'));
    if (signup && password !== values.get('confirm_password')) return setError("Passwords don't match.");
    setPending(true);
    setError('');
    try {
      await authenticate(signup ? '/auth/signup' : '/auth/login', signup
        ? { name: String(values.get('name')), email: String(values.get('email')), password }
        : { email: String(values.get('email')), password });
      navigate('/');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Authentication failed. Please try again.');
    } finally {
      setPending(false);
    }
  }

  return <main className="auth-page grid min-h-screen bg-voyager-navy text-voyager-text-primary md:grid-cols-[1.2fr_.8fr]">
    <section className="stitch-grid relative hidden overflow-hidden p-10 md:flex md:flex-col md:justify-between">
      <a href="/" className="relative z-10 flex items-center gap-3 font-display text-xl font-bold"><img src={officialLogo} alt="DBVoyager logo" className="size-12 rounded-xl" />DBVoyager</a>
      <div className="relative z-10 max-w-xl"><p className="font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">Autonomous database engineering</p><h1 className="mt-5 font-display text-5xl font-bold leading-tight">Your database never sleeps. <span className="text-voyager-blue">Neither do we.</span></h1><p className="mt-5 max-w-lg text-lg leading-8 text-voyager-text-secondary">Monitor, diagnose, and improve every PostgreSQL workload with a tireless AI partner.</p></div>
      <div className="relative z-10 flex gap-3 text-sm text-voyager-text-secondary"><span className="voyager-card px-3 py-2">◉ Proactive monitoring</span><span className="voyager-card px-3 py-2">✦ BI chat</span><span className="voyager-card px-3 py-2">✓ One-click fixes</span></div>
    </section>
    <section className="flex items-center justify-center p-6 sm:p-10"><div className="w-full max-w-md">
      <a href="/" className="mb-12 flex items-center gap-2 font-display text-lg font-bold md:hidden"><img src={officialLogo} alt="DBVoyager logo" className="size-9 rounded-lg" />DBVoyager</a>
      <p className="font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">{signup ? 'Start your journey' : 'Welcome back'}</p>
      <h2 className="mt-3 font-display text-3xl font-bold">{signup ? 'Create your account' : 'Sign in to DBVoyager'}</h2>
      <p className="mt-3 text-voyager-text-secondary">{signup ? 'Start exploring your PostgreSQL data in minutes.' : 'Continue to your autonomous database workspace.'}</p>
      <form className="mt-8 space-y-5" onSubmit={submit}>
        {signup && <label className="block text-sm font-medium">Full name<input required name="name" minLength={1} maxLength={100} autoComplete="name" className="auth-input" placeholder="Ada Lovelace" /></label>}
        <label className="block text-sm font-medium">Work email<input required name="email" type="email" minLength={3} maxLength={320} autoComplete="email" className="auth-input" placeholder="you@company.com" /></label>
        <label className="block text-sm font-medium">Password<input required name="password" type="password" minLength={8} maxLength={256} autoComplete={signup ? 'new-password' : 'current-password'} className="auth-input" placeholder="At least 8 characters" /></label>
        {signup && <label className="block text-sm font-medium">Confirm password<input required name="confirm_password" type="password" minLength={8} autoComplete="new-password" className="auth-input" placeholder="Repeat your password" /></label>}
        {error && <p role="alert" className="rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 px-3 py-2 text-sm text-voyager-critical">{error}</p>}
        <button disabled={pending} className="w-full rounded-lg bg-voyager-blue px-5 py-3 font-semibold text-voyager-navy transition hover:bg-voyager-blue-light disabled:cursor-wait disabled:opacity-60">{pending ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button>
      </form>
      <p className="mt-7 text-center text-sm text-voyager-text-secondary">{signup ? 'Already have an account?' : "Don't have an account?"} <a className="font-semibold text-voyager-blue hover:underline" href={signup ? '/login' : '/signup'}>{signup ? 'Sign in' : 'Create one'}</a></p>
    </div></section>
  </main>;
}
