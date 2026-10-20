'use client';

import React, { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { ClinicSidebar } from './_components/ClinicSidebar';
import { ClinicHeader } from './_components/ClinicHeader';
import { QuickBookingModal } from './_components/QuickBookingModal';
import { VoiceSimulatorModal } from './_components/VoiceSimulatorModal';
import { ClinicMobileBottomBar } from './_components/ClinicMobileBottomBar';
import { useClinicStore } from './store';
import { useClinicRealTimeSync } from './_hooks/useClinicQueries';
import { CLINIC_NAV_ITEMS } from './constants';
import { useQueryClient } from '@tanstack/react-query';
import { useClinicBootstrap } from './_hooks/useClinicBootstrap';
import { mapClinicSettings } from './_hooks/useClinicQuery';
import { ApiError } from '@/lib/api/httpClient';

interface ClinicLayoutProps {
  children: React.ReactNode;
}

export default function ClinicLayout({ children }: ClinicLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();

  const queryClient = useQueryClient();
  const bootstrap = useClinicBootstrap();
  const [sessionReady, setSessionReady] = useState(false);

  const [doctorName, setDoctorName] = useState('Doctor');
  const [specialty, setSpecialty] = useState('General Practice');
  const [clinicName, setClinicName] = useState('Clinic Portal');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [voiceSimulatorOpen, setVoiceSimulatorOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('clinic_sidebar_collapsed');
      if (saved !== null) {
        setSidebarCollapsed(saved === 'true');
      }
    }
  }, []);

  const toggleSidebarCollapsed = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== 'undefined') {
        localStorage.setItem('clinic_sidebar_collapsed', String(next));
      }
      return next;
    });
  };

  const setBookingModalOpen = useClinicStore((s) => s.setBookingModalOpen);
  const setBookingModalType = useClinicStore((s) => s.setBookingModalType);
  const setTenantSession = useClinicStore((s) => s.setTenantSession);
  const setActiveRole = useClinicStore((s) => s.setActiveRole);
  const activeRole = useClinicStore((s) => s.activeRole);
  const currentOrgId = useClinicStore((s) => s.orgId);
  useClinicRealTimeSync(sessionReady ? currentOrgId : null);

  const doctorOnlyRoute = pathname === '/clinic' || ['/clinic/patients', '/clinic/revenue', '/clinic/analytics', '/clinic/settings'].some((path) => pathname === path || pathname.startsWith(`${path}/`));
  const needsRoleRedirect = bootstrap.data?.role === 'receptionist' && doctorOnlyRoute;

  useEffect(() => {
    if (bootstrap.error instanceof ApiError && bootstrap.error.status === 401) router.replace('/login');
    const data = bootstrap.data;
    if (!data) return;
    const previous = useClinicStore.getState();
    if (previous.orgId !== data.membership.org_id || previous.doctorId !== data.user.id) {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'clinic-bootstrap' });
      useClinicStore.setState({ ...useClinicStore.getInitialState() });
    }
    setActiveRole(data.role);
    setTenantSession(data.membership.org_id, data.user.id);
    const settings = mapClinicSettings(data.membership, data.user.email);
    queryClient.setQueryData(['clinic-settings', data.membership.org_id, data.user.id], settings);
    queryClient.setQueryData(['clinic-organization', data.membership.org_id], data.organization);
    localStorage.setItem('clinic_org_id', data.membership.org_id);
    localStorage.removeItem('clinic_staff_session');
    setClinicName(settings.clinicName);
    setDoctorName(data.role === 'receptionist' ? data.membership.full_name || 'Front Desk Staff' : settings.doctorName);
    setSpecialty(data.role === 'receptionist' ? 'Reception & Triage' : settings.specialty);
    setSessionReady(true);
  }, [bootstrap.data, bootstrap.error, queryClient, router, setActiveRole, setTenantSession]);

  useEffect(() => {
    if (needsRoleRedirect) router.replace('/clinic/schedule');
  }, [needsRoleRedirect, router]);

  useEffect(() => {
    const { data: { subscription } } = createClient().auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT' || (event === 'SIGNED_IN' && bootstrap.data && session?.user.id !== bootstrap.data.user.id)) {
        setSessionReady(false);
        queryClient.clear();
        useClinicStore.setState({ ...useClinicStore.getInitialState() });
        localStorage.removeItem('clinic_org_id');
        window.location.href = '/login';
      }
    });
    return () => subscription.unsubscribe();
  }, [bootstrap.data, queryClient]);

  const handleSignOut = async () => {
    try {
      const supabase = createClient();
      await supabase.auth.signOut();
    } catch {
    } finally {
      if (typeof window !== 'undefined') {
        const dismissed = localStorage.getItem('dispatch_onboarding_dismissed');
        const keysToKeep = Object.keys(localStorage).filter((k) => k.startsWith('dispatch_onboarding_'));
        const preserved: Record<string, string> = {};
        for (const k of keysToKeep) {
          const v = localStorage.getItem(k);
          if (v) preserved[k] = v;
        }

        localStorage.clear();
        sessionStorage.clear();
        document.cookie = 'clinic_staff_session=; path=/; max-age=0; SameSite=Lax';

        if (dismissed) localStorage.setItem('dispatch_onboarding_dismissed', dismissed);
        for (const [k, v] of Object.entries(preserved)) {
          localStorage.setItem(k, v);
        }

        window.location.href = '/login';
      }
    }
  };

  const pageTitle =
    [...CLINIC_NAV_ITEMS]
      .sort((a, b) => b.href.length - a.href.length)
      .find((item) =>
        item.href === '/clinic' ? pathname === '/clinic' : pathname?.startsWith(item.href)
      )?.label ?? '';

  const initials = doctorName
    .replace(/^Dr\.\s*/, '')
    .split(' ')
    .map((w: string) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  if (!sessionReady || needsRoleRedirect) {
    return <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[#F1F4EE] text-sm text-[rgba(13,38,34,0.7)]">
        {!bootstrap.isError && <Loader2 className="h-5 w-5 animate-spin text-[#1E6B56]" />}
        <p role={bootstrap.isError ? 'alert' : 'status'}>{bootstrap.isError ? 'Could not load your clinic session.' : 'Setting up your clinic workspace...'}</p>
      {bootstrap.isError && <div className="flex gap-4">
        {bootstrap.error instanceof ApiError && bootstrap.error.status === 403 && <button onClick={() => router.push('/signup')} className="font-semibold underline text-[#0D2622]">Complete clinic setup</button>}
        <button onClick={() => void bootstrap.refetch()} className="font-semibold underline text-[#0D2622]">Try again</button>
        <button onClick={() => void handleSignOut()} className="underline text-[#0D2622]">Sign out</button>
      </div>}
    </div>;
  }

  return (
    <div className="h-screen w-screen bg-[#F1F4EE] text-[#0D2622] flex font-sans overflow-hidden selection:bg-[#F4B63A] selection:text-[#0D2622]">
      <ClinicSidebar
        mobileMenuOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
        pathname={pathname}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebarCollapsed}
        clinicName={clinicName}
        specialty={specialty}
        onOpenVoiceSimulator={() => setVoiceSimulatorOpen(true)}
      />

      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <ClinicHeader
          clinicName={clinicName}
          specialty={specialty}
          doctorName={doctorName}
          initials={initials}
          pageTitle={pageTitle}
          activeRole={activeRole}
          mobileMenuOpen={mobileMenuOpen}
          onToggleMobile={() => setMobileMenuOpen(!mobileMenuOpen)}
          onOpenVoiceSimulator={() => setVoiceSimulatorOpen(true)}
          onOpenBooking={() => {
            setBookingModalType('Pre-booked');
            setBookingModalOpen(true);
          }}
          onSignOut={handleSignOut}
        />

        <main
          className={`flex-1 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden flex flex-col pb-20 lg:pb-0 ${pathname?.startsWith('/clinic/settings') ? '' : 'p-3 sm:p-4 lg:p-5 pb-28 lg:pb-5'
            }`}
        >
          <div className="w-full flex-1 flex flex-col min-h-0">{children}</div>
        </main>
      </div>

      <ClinicMobileBottomBar />

      <QuickBookingModal />

      <VoiceSimulatorModal
        isOpen={voiceSimulatorOpen}
        onClose={() => setVoiceSimulatorOpen(false)}
        orgId={currentOrgId || undefined}
      />
    </div>
  );
}
