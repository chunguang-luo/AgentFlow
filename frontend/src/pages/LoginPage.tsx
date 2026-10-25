import { KeyRound, LogIn, User } from 'lucide-react';
import { useState } from 'react';

import { useAuth } from '../auth';

export function LoginPage() {
  const { logIn } = useAuth();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await logIn(username, password);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-brand">
          <span>AF</span>
          <div>
            <strong>AgentFlow</strong>
            <small>Agent workflow operations</small>
          </div>
        </div>

        <form onSubmit={submit}>
          <label>
            <span>Username</span>
            <div className="input-icon">
              <User size={16} />
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
              />
            </div>
          </label>

          <label>
            <span>Password</span>
            <div className="input-icon">
              <KeyRound size={16} />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
          </label>

          {error && <div className="form-error">{error}</div>}

          <button className="primary-button" type="submit" disabled={submitting}>
            <LogIn size={16} />
            <span>{submitting ? 'Signing in' : 'Sign in'}</span>
          </button>
        </form>
      </section>
    </main>
  );
}
