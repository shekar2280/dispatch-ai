'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { createClient } from '@/lib/supabase/client';
import { Loader2, Eye, EyeOff, ShieldAlert, ArrowRight } from 'lucide-react';

const inputCls =
  'h-11 w-full rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#F1F4EE]/40 px-3.5 text-sm text-[#0D2622] shadow-[0_1px_2px_rgba(13,38,34,0.02)] outline-none transition-all placeholder:text-[rgba(13,38,34,0.4)] focus:bg-white focus:border-[#0D2622] focus:ring-4 focus:ring-[#1E6B56]/10';
const labelCls = 'mb-1.5 block text-xs font-semibold text-[#0D2622]';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('error') === 'confirmation_failed') {
      setError('The sign-in link is invalid or expired. Please try again.');
    }
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { data, error: authError } = await createClient().auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (authError || !data?.session) {
        setError(authError?.message || 'Invalid email or password.');
        return;
      }
      window.location.assign('/clinic');
    } catch {
      setError('Sign in is temporarily unavailable. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setGoogleLoading(true);
    setError(null);
    try {
      const { error: authError } = await createClient().auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      });
      if (authError) setError(authError.message);
    } catch {
      setError('Google sign in is temporarily unavailable. Please try again.');
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#0D2622]">Sign in</h1>
        <p className="mt-1 text-xs sm:text-[13px] text-[rgba(13,38,34,0.65)]">
          Access your clinic dashboard, queue, and call records.
        </p>
      </div>

      {error && (
        <div role="alert" className="mb-5 flex items-start gap-2.5 rounded-xl border border-red-200/80 bg-red-50/80 p-3 text-xs font-medium text-red-700">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      )}

      <button
        type="button"
        onClick={handleGoogleLogin}
        disabled={googleLoading || loading}
        className="relative flex h-11 w-full items-center justify-center gap-3 rounded-xl border border-[rgba(13,38,34,0.16)] bg-white text-[13.5px] font-medium text-[#0D2622] shadow-[0_1px_2px_rgba(13,38,34,0.04)] transition hover:bg-[#F1F4EE] hover:border-[rgba(13,38,34,0.24)] active:scale-[0.99] disabled:opacity-50"
      >
        {googleLoading ? (
          <Loader2 className="h-4 w-4 animate-spin text-[#1E6B56]" />
        ) : (
          <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
          </svg>
        )}
        <span>Continue with Google</span>
      </button>

      <div className="relative my-5 flex items-center justify-center">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-[rgba(13,38,34,0.12)]" />
        </div>
        <span className="relative bg-white px-3 text-[11px] font-medium uppercase tracking-wider text-[rgba(13,38,34,0.45)]">
          or email
        </span>
      </div>

      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label htmlFor="login-email" className={labelCls}>Email address</label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="doctor@yourclinic.com"
            className={inputCls}
          />
        </div>

        <div>
          <label htmlFor="login-password" className={labelCls}>Password</label>
          <div className="relative">
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              className={`${inputCls} pr-10`}
            />
            <button
              type="button"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[rgba(13,38,34,0.4)] transition hover:text-[#0D2622]"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || googleLoading}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#0D2622] text-sm font-semibold text-[#F1F4EE] shadow-sm transition hover:bg-[#143530] active:scale-[0.99] disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-[#BFDDCD]" />
          ) : (
            <>
              Sign in <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>
      </form>

      <div className="mt-6 border-t border-[rgba(13,38,34,0.08)] pt-5 text-center text-xs text-[rgba(13,38,34,0.65)]">
        New clinic on Dispatch?{' '}
        <Link href="/signup" className="font-semibold text-[#0D2622] underline underline-offset-4 hover:text-[#1E6B56]">
          Create account
        </Link>
      </div>
    </>
  );
}
