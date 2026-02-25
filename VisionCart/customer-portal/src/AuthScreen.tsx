/**
 * VisionCart – Auth Screen (Login / Signup)
 *
 * First screen shown when customer visits the portal.
 * Allows signup with address details or login with existing credentials.
 */

import React, { useState } from 'react';
import { useStore } from './store';

interface AuthScreenProps {
  onAuthSuccess: () => void;
}

export default function AuthScreen({ onAuthSuccess }: AuthScreenProps) {
  const [isSignup, setIsSignup] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Form fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [addressLine1, setAddressLine1] = useState('');
  const [addressLine2, setAddressLine2] = useState('');
  const [state, setState] = useState('');
  const [zipCode, setZipCode] = useState('');

  const store = useStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (isSignup) {
        // Validate passwords match
        if (password !== confirmPassword) {
          setError('Passwords do not match');
          setIsLoading(false);
          return;
        }

        // Signup API call
        const res = await fetch('/api/customer/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username,
            password,
            address_line_1: addressLine1 || null,
            address_line_2: addressLine2 || null,
            state: state || null,
            zip_code: zipCode || null,
          }),
        });

        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || 'Signup failed');
        }

        // Store customer info and proceed
        store.login(data.customer);
        onAuthSuccess();
      } else {
        // Login API call
        const res = await fetch('/api/customer/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });

        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || 'Login failed');
        }

        // Store customer info and proceed
        store.login(data.customer);
        onAuthSuccess();
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        {/* Logo / Header */}
        <div style={styles.header}>
          <span style={styles.logo}>🛒</span>
          <h1 style={styles.title}>VisionCart</h1>
          <p style={styles.subtitle}>
            {isSignup ? 'Create your account' : 'Welcome back'}
          </p>
        </div>

        {/* Error message */}
        {error && (
          <div style={styles.error}>
            ⚠️ {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          {/* Username */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              required
              minLength={3}
              style={styles.input}
            />
          </div>

          {/* Password */}
          <div style={styles.inputGroup}>
            <label style={styles.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
              minLength={6}
              style={styles.input}
            />
          </div>

          {/* Signup-only fields */}
          {isSignup && (
            <>
              {/* Confirm Password */}
              <div style={styles.inputGroup}>
                <label style={styles.label}>Confirm Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter password"
                  required
                  style={styles.input}
                />
              </div>

              <div style={styles.divider}>
                <span style={styles.dividerText}>Delivery Address (Optional)</span>
              </div>

              {/* Address Line 1 */}
              <div style={styles.inputGroup}>
                <label style={styles.label}>Address Line 1</label>
                <input
                  type="text"
                  value={addressLine1}
                  onChange={(e) => setAddressLine1(e.target.value)}
                  placeholder="Street address"
                  style={styles.input}
                />
              </div>

              {/* Address Line 2 */}
              <div style={styles.inputGroup}>
                <label style={styles.label}>Address Line 2</label>
                <input
                  type="text"
                  value={addressLine2}
                  onChange={(e) => setAddressLine2(e.target.value)}
                  placeholder="Apt, suite, unit (optional)"
                  style={styles.input}
                />
              </div>

              {/* State & Zip */}
              <div style={styles.row}>
                <div style={{ ...styles.inputGroup, flex: 1 }}>
                  <label style={styles.label}>State</label>
                  <input
                    type="text"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    placeholder="CA"
                    style={styles.input}
                  />
                </div>
                <div style={{ ...styles.inputGroup, flex: 1 }}>
                  <label style={styles.label}>Zip Code</label>
                  <input
                    type="text"
                    value={zipCode}
                    onChange={(e) => setZipCode(e.target.value)}
                    placeholder="12345"
                    style={styles.input}
                  />
                </div>
              </div>
            </>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading}
            style={{
              ...styles.submitBtn,
              opacity: isLoading ? 0.7 : 1,
              cursor: isLoading ? 'not-allowed' : 'pointer',
            }}
          >
            {isLoading
              ? '⏳ Please wait...'
              : isSignup
                ? '🚀 Create Account'
                : '🔓 Login'}
          </button>
        </form>

        {/* Toggle Login/Signup */}
        <div style={styles.toggleContainer}>
          <span style={styles.toggleText}>
            {isSignup ? 'Already have an account?' : "Don't have an account?"}
          </span>
          <button
            type="button"
            onClick={() => {
              setIsSignup(!isSignup);
              setError('');
            }}
            style={styles.toggleBtn}
          >
            {isSignup ? 'Login' : 'Sign Up'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 50%, #0a0a0f 100%)',
    padding: '40px 20px',
    overflowY: 'auto' as const,
    boxSizing: 'border-box' as const,
  },
  card: {
    width: '100%',
    maxWidth: '420px',
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    borderRadius: '24px',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    padding: '40px 32px',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
  },
  header: {
    textAlign: 'center' as const,
    marginBottom: '32px',
  },
  logo: {
    fontSize: '48px',
    display: 'block',
    marginBottom: '8px',
  },
  title: {
    color: '#ffffff',
    fontSize: '28px',
    fontWeight: 700,
    margin: '0 0 8px 0',
    letterSpacing: '-0.5px',
  },
  subtitle: {
    color: '#888',
    fontSize: '14px',
    margin: 0,
  },
  error: {
    background: 'rgba(255, 51, 51, 0.1)',
    border: '1px solid rgba(255, 51, 51, 0.3)',
    borderRadius: '10px',
    padding: '12px 16px',
    marginBottom: '20px',
    color: '#FF5555',
    fontSize: '14px',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '16px',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
  },
  label: {
    color: '#aaa',
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  input: {
    background: 'rgba(255, 255, 255, 0.06)',
    border: '1px solid rgba(255, 255, 255, 0.12)',
    borderRadius: '10px',
    padding: '14px 16px',
    color: '#e0e0e0',
    fontSize: '15px',
    outline: 'none',
    transition: 'border-color 0.2s, background 0.2s',
  },
  row: {
    display: 'flex',
    gap: '12px',
  },
  divider: {
    textAlign: 'center' as const,
    margin: '8px 0',
    position: 'relative' as const,
  },
  dividerText: {
    color: '#666',
    fontSize: '11px',
    textTransform: 'uppercase' as const,
    letterSpacing: '1px',
    background: 'transparent',
    padding: '0 12px',
  },
  submitBtn: {
    background: 'linear-gradient(135deg, #00D4FF 0%, #00FF88 100%)',
    border: 'none',
    borderRadius: '12px',
    padding: '16px 24px',
    color: '#000',
    fontSize: '15px',
    fontWeight: 700,
    marginTop: '8px',
    transition: 'transform 0.2s, box-shadow 0.2s',
  },
  toggleContainer: {
    marginTop: '24px',
    textAlign: 'center' as const,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
  },
  toggleText: {
    color: '#888',
    fontSize: '14px',
  },
  toggleBtn: {
    background: 'transparent',
    border: 'none',
    color: '#00D4FF',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    textDecoration: 'underline',
  },
};
