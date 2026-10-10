import { useState } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, Eye, EyeOff, FlaskConical, LoaderCircle, Lock, TriangleAlert, User } from 'lucide-react';

export default function LoginScreen({ onLogin, loading, error }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    onLogin(username.trim(), password);
  };

  return (
    <div className="login-shell">
      <aside className="login-brand">
        <div className="login-brand-pattern" aria-hidden="true" />
        <div className="login-brand-glow" aria-hidden="true" />

        <motion.div
          className="login-brand-inner"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        >
          <div className="login-logo">
            <span className="brand-mark brand-mark-light">
              <FlaskConical size={18} strokeWidth={2.2} />
            </span>
            ChemSentry
          </div>

          <h1 className="login-headline">Chemical storage safety, grounded in the source.</h1>

          <div className="login-brand-footer">© {new Date().getFullYear()} ChemSentry</div>
        </motion.div>
      </aside>

      <main className="login-main">
        <motion.div
          className="login-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: 'easeOut', delay: 0.1 }}
        >
          <div className="login-mobile-logo">
            <span className="brand-mark">
              <FlaskConical size={16} strokeWidth={2.2} />
            </span>
            ChemSentry
          </div>

          <h2>Sign in</h2>
          <p className="login-sub">Welcome back. Enter your account details.</p>

          <form onSubmit={handleSubmit} className="login-form">
            <label className="field">
              <span className="field-label">Username</span>
              <span className="input-with-icon">
                <User size={16} aria-hidden="true" />
                <input
                  className="input-field"
                  autoComplete="username"
                  placeholder="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </span>
            </label>

            <label className="field">
              <span className="field-label">Password</span>
              <span className="input-with-icon">
                <Lock size={16} aria-hidden="true" />
                <input
                  className="input-field"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="input-icon-btn"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </span>
            </label>

            {error && (
              <motion.div
                className="login-error"
                role="alert"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <TriangleAlert size={15} aria-hidden="true" />
                {error}
              </motion.div>
            )}

            <button type="submit" className="action-btn btn-block btn-lg" disabled={loading}>
              {loading ? (
                <>
                  <LoaderCircle size={16} className="spin" /> Signing in
                </>
              ) : (
                <>
                  Sign in <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        </motion.div>
      </main>
    </div>
  );
}
