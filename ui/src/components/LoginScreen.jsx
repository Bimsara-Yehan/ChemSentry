import { useState } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, Eye, EyeOff, LoaderCircle, Lock, TriangleAlert, User } from 'lucide-react';
import Flask from './Flask';
import MoleculeField from './MoleculeField';
import { rise, stagger } from './motionVariants';

export default function LoginScreen({ onLogin, loading, error, restoring }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    onLogin(username.trim(), password);
  };

  return (
    <div className="login-shell">
      <MoleculeField density={1.1} />
      <div className="login-aurora" aria-hidden="true" />

      <motion.section className="login-brand" variants={stagger} initial="hidden" animate="show">
        <motion.div className="brand-lockup" variants={rise}>
          <span className="brand-hex">
            <span>Cs</span>
          </span>
          <span className="brand-name">ChemSentry</span>
        </motion.div>

        <motion.h1 className="login-headline" variants={rise}>
          Chemical storage safety, <span className="gradient-text">grounded in the source.</span>
        </motion.h1>
        <motion.p className="login-lede" variants={rise}>
          Sensors detect a change. ChemSentry retrieves the governing limit from the Safety Data Sheet,
          reconciles supplier evidence, and reaches a deterministic verdict before anyone is alerted.
        </motion.p>


        <motion.div className="login-flask" variants={rise} aria-hidden="true">
          <Flask size={150} level={0.5} />
          <div className="flask-shadow" />
        </motion.div>
      </motion.section>

      <main className="login-main">
        <motion.div
          className="login-card glass"
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: 'spring', stiffness: 180, damping: 22, delay: 0.15 }}
        >
          {restoring ? (
            <div className="login-restoring">
              <Flask size={64} level={0.55} />
              <p>Restoring your session…</p>
            </div>
          ) : (
            <>
              <div className="login-card-head">
                <span className="hazard-stripe" aria-hidden="true" />
                <h2>Sign in</h2>
                <p className="login-sub">Use the account issued by your safety administrator.</p>
              </div>

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
                      autoFocus
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
                    initial={{ opacity: 0, x: 0 }}
                    animate={{ opacity: 1, x: [0, -8, 8, -5, 5, 0] }}
                    transition={{ duration: 0.4 }}
                  >
                    <TriangleAlert size={15} aria-hidden="true" />
                    {error}
                  </motion.div>
                )}

                <motion.button
                  type="submit"
                  className="action-btn btn-block btn-lg btn-glow"
                  disabled={loading}
                  whileHover={{ scale: 1.015 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {loading ? (
                    <>
                      <LoaderCircle size={16} className="spin" /> Signing in
                    </>
                  ) : (
                    <>
                      Sign in <ArrowRight size={16} />
                    </>
                  )}
                </motion.button>
              </form>
            </>
          )}
        </motion.div>
        <p className="login-foot">© {new Date().getFullYear()} ChemSentry</p>
      </main>
    </div>
  );
}
