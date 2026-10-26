'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { createClient } from '@/lib/supabase/client';
import { ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, Eye, EyeOff, Loader2, ShieldAlert } from 'lucide-react';
import { ALL_COUNTRIES, ALL_CURRENCIES, getAllTimezonesList, getCountryProfile, getCurrencyForCode, getTimezonesForCountryCode } from '@/lib/country-metadata';
import { Select } from '@/components/ui/Select';

const CLINIC_SPECIALTIES = [
  'General Practice',
  'Pediatrics',
  'Dermatology',
  'Dentistry',
  'Gynecology',
  'Orthopedics',
  'ENT (Ear, Nose & Throat)',
  'Ophthalmology',
  'Cardiology',
  'Neurology',
  'Psychiatry & Mental Health',
  'Physiotherapy',
  'Gastroenterology',
  'Endocrinology',
  'Urology',
  'Other',
];
const ALL_TIMEZONES = getAllTimezonesList();

const inputCls =
  'h-11 w-full rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#F1F4EE]/40 px-3.5 text-sm text-[#0D2622] shadow-[0_1px_2px_rgba(13,38,34,0.02)] outline-none transition-all placeholder:text-[rgba(13,38,34,0.4)] focus:bg-white focus:border-[#0D2622] focus:ring-4 focus:ring-[#1E6B56]/10';
const labelCls = 'mb-1.5 block text-xs font-semibold text-[#0D2622]';
const primaryBtn =
  'flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#0D2622] text-sm font-semibold text-[#F1F4EE] shadow-sm transition hover:bg-[#143530] active:scale-[0.99] disabled:opacity-50';

export default function SignupPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [oauthUserId, setOauthUserId] = useState<string | null>(null);

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [orgName, setOrgName] = useState('');
  const [clinicSpecialty, setClinicSpecialty] = useState('');
  const [city, setCity] = useState('');
  const [address, setAddress] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [currencyCode, setCurrencyCode] = useState('');
  const [timezone, setTimezone] = useState('');
  const [emergencyPhone, setEmergencyPhone] = useState('');
  const [phone, setPhone] = useState('');

  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [needsEmailConfirmation, setNeedsEmailConfirmation] = useState(false);

  const countryProfile = getCountryProfile(countryCode);
  const countryTimezones = getTimezonesForCountryCode(countryCode);
  const countryTimezoneValues = new Set(countryTimezones.map((tz) => tz.value));

  useEffect(() => {
    let active = true;
    const checkExistingSession = async () => {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (!user || !active) return;
      const { data: existingUser, error: membershipError } = await supabase
        .from('users').select('org_id').eq('id', user.id).maybeSingle();
      if (!active || membershipError) return;
      if (existingUser?.org_id) {
        router.replace('/clinic');
        return;
      }
      setOauthUserId(user.id);
      setFullName(String(user.user_metadata?.full_name || user.user_metadata?.name || ''));
      setEmail(user.email || '');
      setStep(2);
    };
    void checkExistingSession();
    return () => { active = false; };
  }, [router]);

  const handleGoogleSignup = async () => {
    setGoogleLoading(true);
    setError(null);
    try {
      const { error: authError } = await createClient().auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}/auth/callback?next=/signup` },
      });
      if (authError) setError(authError.message);
    } catch {
      setError('Google sign up is temporarily unavailable. Please try again.');
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleStepOne = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || !password) {
      setError('Please fill in your name, email, and password.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setError(null);
    setStep(2);
  };

  const handleFinalSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !orgName.trim() || !city.trim() || !clinicSpecialty || !countryCode || !currencyCode || !timezone || !emergencyPhone.trim()) {
      setError('Please provide the doctor name, clinic name, city, specialty, country, currency, timezone, and emergency contact.');
      return;
    }
    if (fullName.length > 120 || orgName.length > 120 || city.length > 120 || address.length > 240 || phone.length > 32 || emergencyPhone.length > 32) {
      setError('One or more fields are too long. Please shorten the clinic details.');
      return;
    }
    setLoading(true);
    setError(null);

    const doctorName = fullName.trim();
    const formattedPhone = phone.trim()
      ? phone.trim().startsWith('+')
        ? phone.trim()
        : `${countryProfile.phoneCode} ${phone.trim().replace(/^0+/, '')}`
      : null;

    const slug = orgName.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-') + '-' + Math.random().toString(36).substring(2, 8);

    const supabase = createClient();
    if (oauthUserId) {
      const { error: rpcError } = await supabase.rpc('register_organization_and_admin', {
        p_org_name: orgName.trim(),
        p_slug: slug,
        p_city: city.trim(),
        p_user_id: oauthUserId,
        p_email: email.trim(),
        p_full_name: fullName.trim(),
        p_clinic_specialty: clinicSpecialty,
        p_lead_doctor_name: doctorName,
        p_phone: formattedPhone,
        p_country: countryProfile.name,
        p_country_code: countryCode,
        p_currency_code: currencyCode,
        p_currency_symbol: getCurrencyForCode(currencyCode).symbol,
        p_timezone: timezone,
        p_address: address.trim() || null,
        p_emergency_phone: emergencyPhone.trim(),
      });
      if (rpcError) {
        setError(rpcError.message);
        setLoading(false);
        return;
      }
      router.push('/clinic');
      router.refresh();
      return;
    }
    const { data: authData, error: authError } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        data: {
          full_name: fullName.trim(),
          org_name: orgName.trim(),
          slug,
          city: city.trim(),
          address: address.trim() || null,
          clinic_specialty: clinicSpecialty,
          lead_doctor_name: doctorName,
          phone: formattedPhone,
          country: countryProfile.name,
          country_code: countryCode,
          currency_code: currencyCode,
          currency_symbol: getCurrencyForCode(currencyCode).symbol,
          timezone,
          emergency_deflection_phone: emergencyPhone.trim(),
        },
      },
    });

    if (authError || !authData.user) {
      setError(authError?.message || 'Failed to create account.');
      setLoading(false);
      return;
    }

    if (!authData.session) {
      setNeedsEmailConfirmation(true);
      setSuccess(true);
      setLoading(false);
      return;
    }

    setTimeout(() => {
      router.push('/clinic');
      router.refresh();
    }, 1200);
  };


  if (success) {
    return (
      <div className="py-6 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-[#BFDDCD] bg-[#E3EBE0] text-[#1E6B56] shadow-sm">
          <CheckCircle2 className="h-7 w-7" />
        </div>
        <h1 className="text-xl font-bold text-[#0D2622]">{needsEmailConfirmation ? 'Check your inbox' : 'Clinic registered'}</h1>
        <p className="mt-1.5 text-xs sm:text-[13px] leading-relaxed text-[rgba(13,38,34,0.65)]">
          {needsEmailConfirmation
            ? 'We sent a verification link to your email. Click it to activate your clinic workspace.'
            : 'Setting up your clinic workspace and routing configuration…'}
        </p>
        {needsEmailConfirmation && (
          <Link
            href="/login"
            className="mt-6 inline-flex h-10 items-center justify-center rounded-xl bg-[#0D2622] px-6 text-xs font-semibold text-[#F1F4EE] shadow-sm transition hover:bg-[#143530]"
          >
            Go to sign in
          </Link>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-[#F1F4EE]/90 backdrop-blur-sm text-sm text-[#0D2622] animate-in fade-in duration-200">
        <Loader2 className="h-5 w-5 animate-spin text-[#1E6B56]" />
        <p className="font-medium text-[#0D2622]">Setting up your clinic workspace...</p>
      </div>
    );
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#0D2622]">
          {step === 1 ? 'Create account' : 'Clinic details'}
        </h1>
        <p className="mt-1 text-xs sm:text-[13px] text-[rgba(13,38,34,0.65)]">
          {step === 1
            ? 'Doctor or administrator identity to manage your practice'
            : 'Operating parameters, specialty, and regional configuration'}
        </p>
      </div>

      {error && (
        <div role="alert" className="mb-5 flex items-start gap-2.5 rounded-xl border border-red-200/80 bg-red-50/80 p-3 text-xs font-medium text-red-700">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      )}

      {step === 1 && (
        <>
          <button
            type="button"
            onClick={handleGoogleSignup}
            disabled={googleLoading}
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

          <form onSubmit={handleStepOne} className="space-y-4">
            <div>
              <label htmlFor="signup-fullname" className={labelCls}>Full name</label>
              <input
                id="signup-fullname"
                type="text"
                required
                autoComplete="name"
                value={fullName}
                maxLength={120}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Dr. Priya Sharma"
                className={inputCls}
              />
            </div>
            <div>
              <label htmlFor="signup-email" className={labelCls}>Work email</label>
              <input
                id="signup-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                maxLength={254}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="doctor@yourclinic.com"
                className={inputCls}
              />
            </div>
            <div>
              <label htmlFor="signup-password" className={labelCls}>Password</label>
              <div className="relative">
                <input
                  id="signup-password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className={`${inputCls} pr-10`}
                />
                <button
                  type="button"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 transition hover:text-stone-700"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <button type="submit" className={primaryBtn}>
              Continue to clinic details <ArrowRight className="h-4 w-4" />
            </button>
          </form>

          <div className="mt-6 border-t border-[rgba(13,38,34,0.08)] pt-5 text-center text-xs text-[rgba(13,38,34,0.65)]">
            Already registered?{' '}
            <Link href="/login" className="font-semibold text-[#0D2622] underline underline-offset-4 hover:text-[#1E6B56]">
              Sign in
            </Link>
          </div>
        </>
      )}

      {step === 2 && (
        <form onSubmit={handleFinalSignup} className="space-y-4">
          {oauthUserId && <div>
            <label htmlFor="signup-doctor-name" className={labelCls}>Doctor / admin name</label>
            <input id="signup-doctor-name" type="text" required value={fullName} maxLength={120} onChange={(e) => setFullName(e.target.value)} className={inputCls} />
          </div>}
          <div>
            <label htmlFor="signup-org-name" className={labelCls}>Clinic / Hospital name</label>
            <input
              id="signup-org-name"
              type="text"
              required
              value={orgName}
              maxLength={120}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="e.g. Apex Multispecialty Clinic"
              className={inputCls}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="signup-specialty" className={labelCls}>Specialty</label>
              <Select
                id="signup-specialty"
                value={clinicSpecialty}
                onChange={setClinicSpecialty}
                placeholder="Select specialty"
                options={CLINIC_SPECIALTIES.map((s) => ({ value: s, label: s }))}
              />
            </div>
            <div>
              <label htmlFor="signup-city" className={labelCls}>City</label>
              <input
                id="signup-city"
                type="text"
                required
                value={city}
              maxLength={120}
                onChange={(e) => setCity(e.target.value)}
                placeholder="e.g. Mumbai"
                className={inputCls}
              />
            </div>
          </div>

          <div>
            <label htmlFor="signup-address" className={labelCls}>
              Street address <span className="font-normal text-stone-400">(optional)</span>
            </label>
            <input
              id="signup-address"
              type="text"
              value={address}
              maxLength={240}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="e.g. Suite 101, Linking Road"
              className={inputCls}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="signup-country" className={labelCls}>Country</label>
              <Select
                id="signup-country"
                value={countryCode}
                onChange={(code) => { setCountryCode(code); setTimezone(''); setCurrencyCode(''); }}
                placeholder="Select country"
                options={ALL_COUNTRIES.map((c) => ({ value: c.code, label: c.name }))}
                openUpwards
              />
            </div>
            <div>
              <label htmlFor="signup-phone" className={labelCls}>Clinic phone</label>
              <div className="flex h-11 items-center overflow-hidden rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#F1F4EE]/40 shadow-[0_1px_2px_rgba(13,38,34,0.02)] transition-all focus-within:bg-white focus-within:border-[#0D2622] focus-within:ring-4 focus-within:ring-[#1E6B56]/10">
                <span className="flex h-full shrink-0 items-center border-r border-[rgba(13,38,34,0.14)] bg-[#E3EBE0]/60 px-3 text-xs font-semibold text-[#0D2622]">
                  {countryProfile.phoneCode}
                </span>
                <input
                  id="signup-phone"
                  type="tel"
                  value={phone}
                  maxLength={32}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="98765 43210"
                  className="h-full w-full min-w-0 bg-transparent px-3 text-sm text-[#0D2622] outline-none placeholder:text-[rgba(13,38,34,0.4)]"
                />
              </div>
            </div>
          </div>

          <div>
            <label htmlFor="signup-currency" className={labelCls}>Billing currency</label>
            <Select
              id="signup-currency"
              value={currencyCode}
              onChange={setCurrencyCode}
              placeholder="Select currency"
              options={ALL_CURRENCIES.map((currency) => ({ value: currency.code, label: `${currency.name} (${currency.code})` }))}
            />
          </div>

          <div>
            <label htmlFor="signup-timezone" className={labelCls}>Clinic timezone</label>
            <Select
              id="signup-timezone"
              value={timezone}
              onChange={setTimezone}
              placeholder="Select timezone"
              options={[
                ...countryTimezones,
                ...ALL_TIMEZONES.filter((tz) => !countryTimezoneValues.has(tz.value)),
              ].map((tz) => ({ value: tz.value, label: tz.label }))}
            />
          </div>

          <div>
            <label htmlFor="signup-emergency" className={labelCls}>Emergency contact number</label>
            <input
              id="signup-emergency"
              type="tel"
              required
              value={emergencyPhone}
              maxLength={32}
              onChange={(e) => setEmergencyPhone(e.target.value)}
              placeholder="Local ambulance or emergency service number"
              className={inputCls}
            />
          </div>

          <div className="flex gap-2.5 pt-2">
            {!oauthUserId && <button
              type="button"
              onClick={() => { setError(null); setStep(1); }}
              disabled={loading}
              className="flex h-11 items-center gap-1.5 rounded-xl border border-[rgba(13,38,34,0.16)] bg-white px-4 text-sm font-semibold text-[#0D2622] shadow-[0_1px_2px_rgba(13,38,34,0.03)] transition hover:bg-[#F1F4EE] hover:border-[rgba(13,38,34,0.24)] active:scale-[0.99] disabled:opacity-50"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>}
            <button type="submit" disabled={loading} className={`${primaryBtn} flex-1`}>
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-[#BFDDCD]" /> Creating clinic…
                </>
              ) : (
                'Complete registration'
              )}
            </button>
          </div>
        </form>
      )}
    </>
  );
}
