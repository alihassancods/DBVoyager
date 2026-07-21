import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { authenticate } from '../lib/auth';

const passwordMessage = 'Use 8+ characters with uppercase, lowercase, and a number.';

function passwordChecks(password: string) {
  return [
    ['8+ characters', password.length >= 8],
    ['Lowercase letter', /[a-z]/.test(password)],
    ['Uppercase letter', /[A-Z]/.test(password)],
    ['Number', /\d/.test(password)],
  ] as const;
}

function passwordError(password: string) {
  return passwordChecks(password).every(([, passed]) => passed) ? '' : passwordMessage;
}

export default function AuthPage({ signup }: { signup: boolean }) {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [passwordValue, setPasswordValue] = useState('');
  const checks = passwordChecks(passwordValue);
  const passedChecks = checks.filter(([, passed]) => passed).length;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const password = String(values.get('password'));
    if (signup && password !== values.get('confirm_password')) return setError("Passwords don't match.");
    if (signup && passwordError(password)) return setError(passwordMessage);
    setPending(true);
    setError('');
    try {
      await authenticate(signup ? '/auth/signup' : '/auth/login', signup
        ? { name: String(values.get('name')), email: String(values.get('email')), password }
        : { email: String(values.get('email')), password });
      navigate('/dashboard', { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Authentication failed. Please try again.');
    } finally {
      setPending(false);
    }
  }

  return <main className="auth-page grid min-h-screen bg-voyager-navy text-voyager-text-primary md:grid-cols-[1.2fr_.8fr]">
    <section className="stitch-grid relative hidden overflow-hidden p-10 md:flex md:flex-col md:justify-between">
      <a href="/" className="relative z-10 flex items-center gap-3 font-display text-xl font-bold"><img src="/screen.png" alt="DBVoyager logo" className="size-12 rounded-xl" />DBVoyager</a>
      <div className="relative z-10 max-w-xl"><p className="font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">Autonomous agentic DBA AI</p><h1 className="mt-5 font-display text-5xl font-bold leading-tight">Your database gets a <span className="text-voyager-blue">second set of eyes.</span></h1><p className="mt-5 max-w-lg text-lg leading-8 text-voyager-text-secondary">DBVoyager watches PostgreSQL, investigates what changed, and prepares safe recommendations for your approval.</p></div>
      <div className="relative z-10 flex gap-3 text-sm text-voyager-text-secondary"><span className="voyager-card px-3 py-2">◉ Observe</span><span className="voyager-card px-3 py-2">✦ Investigate</span><span className="voyager-card px-3 py-2">✓ Recommend</span></div>
    </section>
    <section className="flex items-center justify-center p-6 sm:p-10"><div className="w-full max-w-md">
      <a href="/" className="mb-12 flex items-center gap-2 font-display text-lg font-bold md:hidden"><img src="/screen.png" alt="DBVoyager logo" className="size-9 rounded-lg" />DBVoyager</a>
      <p className="font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">{signup ? 'Deploy your DBA AI' : 'Welcome back'}</p>
      <h2 className="mt-3 font-display text-3xl font-bold">{signup ? 'Give your database a second set of eyes.' : 'Return to your DBA AI workspace.'}</h2>
      <p className="mt-3 text-voyager-text-secondary">{signup ? 'Create your account, then connect PostgreSQL to surface the signals that matter.' : 'Your database operations are waiting.'}</p>
      <form className="mt-8 space-y-5" onSubmit={submit}>
        {signup && <label className="block text-sm font-medium">Full name<input required name="name" minLength={1} maxLength={100} autoComplete="name" className="auth-input" placeholder="Ada Lovelace" /></label>}
        <label className="block text-sm font-medium">Work email<input required name="email" type="email" minLength={3} maxLength={320} autoComplete="email" className="auth-input" placeholder="you@company.com" /></label>
        <label className="block text-sm font-medium">Password<input required name="password" type="password" minLength={signup ? 8 : 1} maxLength={256} autoComplete={signup ? 'new-password' : 'current-password'} className="auth-input" placeholder={signup ? passwordMessage : 'Your password'} aria-describedby={signup ? 'password-requirements' : undefined} onChange={event => setPasswordValue(event.target.value)} /></label>
        {signup && <div id="password-requirements" className="-mt-3 text-xs text-voyager-text-secondary" aria-live="polite"><p>{passwordValue ? `${passedChecks}/4 requirements met` : passwordMessage}</p><ul className="mt-1 grid grid-cols-2 gap-1">{checks.map(([label, passed]) => <li key={label} className={passed ? 'text-voyager-success' : ''}>{passed ? '✓' : '○'} {label}</li>)}</ul></div>}
        {signup && <label className="block text-sm font-medium">Confirm password<input required name="confirm_password" type="password" minLength={8} autoComplete="new-password" className="auth-input" placeholder="Repeat your password" /></label>}
        {error && <p role="alert" className="rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 px-3 py-2 text-sm text-voyager-critical">{error}</p>}
        <button disabled={pending} className="w-full rounded-lg bg-voyager-blue px-5 py-3 font-semibold text-voyager-navy transition hover:bg-voyager-blue-light disabled:cursor-wait disabled:opacity-60">{pending ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button>
      </form>
      <p className="mt-7 text-center text-sm text-voyager-text-secondary">{signup ? 'Already have an account?' : "Don't have an account?"} <a className="font-semibold text-voyager-blue hover:underline" href={signup ? '/login' : '/signup'}>{signup ? 'Sign in' : 'Create one'}</a></p>
    </div></section>
  </main>;
}
