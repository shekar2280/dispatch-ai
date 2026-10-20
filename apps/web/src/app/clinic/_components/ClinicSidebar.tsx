'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { APP_CONFIG } from '@/lib/constants';
import { CLINIC_NAV_ITEMS } from '../constants';
import { useClinicStore } from '../store';
import {
  UserCheck,
  CheckCheck,
  Stethoscope,
  Building2,
  PanelLeftClose,
  PanelLeftOpen,
  LayoutGrid,
  CalendarClock,
  Phone,
  Users,
  Inbox,
  Receipt,
  BarChart3,
  Settings2,
  type LucideIcon,
} from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import Image from 'next/image';
import { useVoiceAllowanceQuery } from '../_hooks/useClinicQueries';

interface ClinicSidebarProps {
  mobileMenuOpen: boolean;
  onCloseMobile: () => void;
  pathname: string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  clinicName?: string;
  specialty?: string;
  onOpenVoiceSimulator: () => void;
}

function resolveIcon(href: string, fallback: LucideIcon): LucideIcon {
  const h = href.toLowerCase();
  if (h.includes('schedule') || h.includes('queue')) return CalendarClock;
  if (h.includes('call') || h.includes('voice')) return Phone;
  if (h.includes('patient')) return Users;
  if (h.includes('action')) return Inbox;
  if (h.includes('revenue') || h.includes('billing')) return Receipt;
  if (h.includes('analytic') || h.includes('report')) return BarChart3;
  if (h.includes('setting')) return Settings2;
  if (h === '/clinic') return LayoutGrid;
  return fallback;
}

export function ClinicSidebar({
  mobileMenuOpen,
  onCloseMobile,
  pathname,
  isCollapsed = false,
  onToggleCollapse,
  clinicName = 'Private Practice',
  specialty = 'General Practice',
  onOpenVoiceSimulator,
}: ClinicSidebarProps) {
  const router = useRouter();
  const activeRole = useClinicStore((s) => s.activeRole);

  const currentOrgId = useClinicStore((s) => s.orgId);
  const missedCallsCount = useClinicStore((s) => s.missedCallsCount);
  const setMissedCallsCount = useClinicStore((s) => s.setMissedCallsCount);
  const lastViewedCallsTimestamp = useClinicStore((s) => currentOrgId ? s.viewedCallsByOrg[currentOrgId] ?? null : null);
  const markCallsAsViewed = useClinicStore((s) => s.markCallsAsViewed);

  const { data: voiceAllowance, isLoading: allowanceLoading } = useVoiceAllowanceQuery(currentOrgId);
  const remainingSeconds = voiceAllowance?.remaining_seconds ?? 1800;
  const remainingMinutes = Math.floor(remainingSeconds / 60);
  const remainingSecs = remainingSeconds % 60;
  const timeFormatted = `${remainingMinutes}:${remainingSecs.toString().padStart(2, '0')}`;

  let allowanceTextClass = 'text-emerald-400';
  let allowanceDotClass = 'bg-emerald-400';
  let allowanceLabel = `${timeFormatted} left`;

  if (allowanceLoading) {
    allowanceTextClass = 'text-zinc-400';
    allowanceDotClass = 'bg-zinc-500 animate-pulse';
    allowanceLabel = '...';
  } else if (remainingSeconds <= 0) {
    allowanceTextClass = 'text-rose-400 font-semibold';
    allowanceDotClass = 'bg-rose-500 animate-ping';
    allowanceLabel = '0:00 (Exhausted)';
  } else if (remainingMinutes < 5) {
    allowanceTextClass = 'text-orange-400 font-medium';
    allowanceDotClass = 'bg-orange-400 animate-pulse';
    allowanceLabel = `${timeFormatted} left`;
  } else if (remainingMinutes <= 10) {
    allowanceTextClass = 'text-amber-400 font-medium';
    allowanceDotClass = 'bg-amber-400';
    allowanceLabel = `${timeFormatted} left`;
  }

  useEffect(() => {
    if (missedCallsCount > 0) {
      document.title = `(${missedCallsCount}) Dispatch AI`;
    } else {
      document.title = 'Dispatch AI';
    }
  }, [missedCallsCount]);

  useEffect(() => {
    if (!currentOrgId) return;
    const supabase = createClient();

    const fetchMissed = async () => {
      const watermarkIso = lastViewedCallsTimestamp
        ? new Date(lastViewedCallsTimestamp).toISOString()
        : new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

      const { count, error } = await supabase
        .from('call_logs')
        .select('id', { count: 'exact', head: true })
        .eq('org_id', currentOrgId)
        .gt('end_time', watermarkIso)
        .or('triage_status.ilike.%missed%,call_outcome.ilike.%missed%,call_outcome.ilike.%caller_abandoned%,call_outcome.ilike.%caller_silent%,call_outcome.ilike.%no_answer%,call_outcome.ilike.%line_busy%,call_outcome.ilike.%service_unavailable%,attended_by.ilike.%unattended%');

      if (error) {
        return;
      }
      const state = useClinicStore.getState();
      if (state.orgId !== currentOrgId || (state.viewedCallsByOrg[currentOrgId] ?? null) !== lastViewedCallsTimestamp) return;
      if (typeof count === 'number') {
        setMissedCallsCount(count);
      }
    };
    fetchMissed();

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') fetchMissed();
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    const channel = supabase
      .channel(`sidebar-calls-${currentOrgId}`)
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'call_logs',
          filter: `org_id=eq.${currentOrgId}`,
        },
        () => fetchMissed()
      )
      .subscribe();

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      supabase.removeChannel(channel);
    };
  }, [currentOrgId, setMissedCallsCount, lastViewedCallsTimestamp]);

  const isNavActive = (href: string) =>
    href === '/clinic' ? pathname === '/clinic' : pathname.startsWith(href);

  const visibleNavItems = CLINIC_NAV_ITEMS.filter((item) =>
    item.roles ? item.roles.includes(activeRole) : true
  );


  return (
    <>
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 flex flex-col h-screen
          bg-white border-r border-[rgba(13,38,34,0.12)]
          transition-all duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:flex shrink-0 select-none
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
          ${isCollapsed ? 'w-[60px]' : 'w-[224px]'}
        `}
      >
        <div
          className={`h-[56px] flex items-center border-b border-[rgba(13,38,34,0.12)] shrink-0 ${isCollapsed ? 'justify-center px-2' : 'justify-between pl-3.5 pr-2.5'
            }`}
        >
          <Link
            href={activeRole === 'doctor' ? '/clinic' : '/clinic/schedule'}
            className="flex items-center gap-2 min-w-0"
            onClick={onCloseMobile}
            title="Dispatch AI"
          >
            <Image
              src={APP_CONFIG.logoPath}
              alt="Dispatch AI"
              width={28}
              height={28}
              className="w-7 h-7 rounded-full object-cover shrink-0"
            />
            {!isCollapsed && (
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="font-['Outfit'] text-[15px] font-extrabold tracking-tight text-[#0D2622] leading-none">
                  Dispatch
                </span>
                <span className="font-['Outfit'] text-[9.5px] font-bold px-1.5 py-[3px] rounded bg-[#0D2622] text-[#F1F4EE] tracking-wide leading-none">
                  AI
                </span>
              </div>
            )}
          </Link>

          {!isCollapsed && onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="hidden lg:flex p-1.5 rounded-md text-[rgba(13,38,34,0.45)] hover:text-[#0D2622] hover:bg-[#F1F4EE] transition cursor-pointer"
              title="Collapse sidebar"
            >
              <PanelLeftClose className="w-[15px] h-[15px]" strokeWidth={1.75} />
            </button>
          )}
        </div>

        {!isCollapsed ? (
          <div className="mx-2.5 mt-2.5 px-2.5 py-2 rounded-lg bg-[#F1F4EE] border border-[rgba(13,38,34,0.1)] flex items-center gap-2 shrink-0">
            <div className="w-6 h-6 rounded-md bg-[#0D2622] text-[#F1F4EE] flex items-center justify-center shrink-0">
              <Building2 className="w-3 h-3" strokeWidth={1.75} />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-[12px] font-bold text-[#0D2622] truncate leading-tight">
                {clinicName}
              </h2>
              <p className="text-[10px] font-medium text-[rgba(13,38,34,0.65)] truncate leading-tight mt-px">
                {specialty}
              </p>
            </div>
            <span className="w-1.5 h-1.5 rounded-full bg-[#1E6B56] shrink-0" />
          </div>
        ) : (
          <div className="pt-2.5 flex justify-center shrink-0" title={`${clinicName} (${specialty})`}>
            <div className="w-8 h-8 rounded-lg bg-[#F1F4EE] border border-[rgba(13,38,34,0.12)] text-[#0D2622] flex items-center justify-center">
              <Building2 className="w-3.5 h-3.5" strokeWidth={1.75} />
            </div>
          </div>
        )}


        <nav
          className={`flex-1 overflow-y-auto py-1.5 space-y-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${isCollapsed ? 'px-2' : 'px-2.5'
            }`}
        >
          {visibleNavItems.map((item) => {
            const Icon = resolveIcon(item.href, item.icon);
            const active = isNavActive(item.href);
            const isCallsItem = item.href === '/clinic/calls';

            return (
              <React.Fragment key={item.href}>
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onCloseMobile}
                  title={isCollapsed ? item.label : undefined}
                  className={`
                  relative flex items-center rounded-lg transition-colors group
                  ${isCollapsed ? 'justify-center h-8' : 'gap-2.5 px-2.5 h-8'}
                  ${active
                      ? 'bg-[#E3EBE0] text-[#0D2622] font-bold'
                      : 'text-[#0D2622]/75 hover:text-[#0D2622] hover:bg-[#F1F4EE] font-semibold'
                    }
                `}
                >
                  {active && (
                    <span className="absolute -left-2.5 top-1/2 -translate-y-1/2 w-[3px] h-3.5 bg-[#1E6B56] rounded-r-full" />
                  )}
                  <Icon
                    strokeWidth={active ? 2.25 : 1.75}
                    className={`w-[15px] h-[15px] shrink-0 transition-colors ${active ? 'text-[#1E6B56]' : 'text-[rgba(13,38,34,0.55)] group-hover:text-[#0D2622]'
                      }`}
                  />
                  {!isCollapsed && (
                    <>
                      <span className="truncate text-[12.5px] tracking-tight">{item.label}</span>
                      {isCallsItem && missedCallsCount > 0 ? (
                        <span className="ml-auto text-[10px] font-bold font-mono min-w-[18px] text-center px-1.5 py-px rounded-full bg-rose-600 text-white">
                          {missedCallsCount}
                        </span>
                      ) : item.badge ? (
                        <span className="ml-auto text-[10px] font-bold px-1.5 py-px rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                          {item.badge}
                        </span>
                      ) : null}
                    </>
                  )}
                  {isCollapsed && isCallsItem && missedCallsCount > 0 && (
                    <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-rose-600 ring-2 ring-white" />
                  )}
                </Link>
                {isCallsItem && missedCallsCount > 0 && !isCollapsed && (
                  <button type="button" onClick={markCallsAsViewed} title="Clear the new missed-call badge. Calls remain in history." className="ml-7 flex min-h-7 items-center gap-1.5 rounded-md px-2 text-[10px] font-medium text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 focus-visible:ring-2 focus-visible:ring-emerald-700"><CheckCheck className="h-3 w-3" />Mark missed calls as seen</button>
                )}
              </React.Fragment>
            );
          })}
        </nav>

        {isCollapsed && (
          <div className="p-2 border-t border-[rgba(13,38,34,0.08)] flex flex-col items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={onOpenVoiceSimulator}
              className="relative p-1.5 rounded-md text-[rgba(13,38,34,0.65)] hover:text-[#0D2622] hover:bg-[#F1F4EE] transition cursor-pointer"
              title={`Credits Remaining (${allowanceLabel})`}
            >
              <Phone className="w-[15px] h-[15px]" strokeWidth={1.75} />
              <span className={`absolute top-1 right-1 w-1.5 h-1.5 rounded-full ${allowanceDotClass}`} />
            </button>
            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                className="p-1.5 rounded-md text-[rgba(13,38,34,0.45)] hover:text-[#0D2622] hover:bg-[#F1F4EE] transition cursor-pointer"
                title="Expand sidebar"
              >
                <PanelLeftOpen className="w-[15px] h-[15px]" strokeWidth={1.75} />
              </button>
            )}
          </div>
        )}

        {!isCollapsed && (
          <div className="p-2.5 border-t border-[rgba(13,38,34,0.08)] shrink-0">
            <button
              type="button"
              onClick={onOpenVoiceSimulator}
              className="w-full text-left block px-2.5 py-2 rounded-lg bg-[#0D2622] text-[#F1F4EE] hover:bg-[#143530] transition-colors group cursor-pointer"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${allowanceDotClass}`} />
                  <span className="text-[11px] font-bold text-[#F1F4EE] truncate">Credits Remaining</span>
                </div>
                <span className={`text-[10px] shrink-0 font-mono font-bold ${allowanceTextClass}`}>
                  {allowanceLabel}
                </span>
              </div>
            </button>
          </div>
        )}
      </aside>

      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-xs lg:hidden"
          onClick={onCloseMobile}
        />
      )}
    </>
  );
}
