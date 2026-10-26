'use client';

import React, { useEffect, useCallback, useMemo, useRef, useState } from 'react';
import {
  Clock,
  Sun,
  Moon,
  Plus,
  DoorClosed,
  ArrowRight,
  Calendar,
  Zap,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Layers,
  RefreshCw,
} from 'lucide-react';
import { ClinicSlotItem } from '../../types';
import { formatDateISO } from '../../utils';
import { parseTimeToMinutes } from '../_utils/timeUtils';
import { ArrivalWindowsSkeleton } from '../../_components/ClinicSkeletons';

/** Fit short lists naturally; desktop shows five rows before scrolling. */
function SlotGrid({ children }: { children: React.ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>();
  const [canScroll, setCanScroll] = useState(false);
  const [atEnd, setAtEnd] = useState(false);
  const [visibleRows, setVisibleRows] = useState(4);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1024px)');
    const updateRows = () => setVisibleRows(query.matches ? 5 : 4);
    updateRows();
    query.addEventListener('change', updateRows);
    return () => query.removeEventListener('change', updateRows);
  }, []);

  useEffect(() => {
    const container = viewport.current;
    const content = grid.current;
    if (!container || !content) return;
    const measure = () => {
      const cards = Array.from(content.children) as HTMLElement[];
      const rows = Array.from(new Set(cards.map(card => card.offsetTop)));
      const finalVisibleRow = rows[visibleRows - 1];
      const limit = finalVisibleRow === undefined
        ? content.scrollHeight
        : Math.max(...cards.filter(card => card.offsetTop === finalVisibleRow).map(card => card.offsetTop + card.offsetHeight));
      setHeight(limit);
      setCanScroll(content.scrollHeight > limit + 1);
      setAtEnd(container.scrollTop + limit >= content.scrollHeight - 2);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(content);
    Array.from(content.children).forEach(child => observer.observe(child));
    measure();
    return () => observer.disconnect();
  }, [children, visibleRows]);

  return (
    <div className="min-w-0">
      <div
        ref={viewport}
        role="region"
        aria-label="Appointment time slots"
        tabIndex={canScroll ? 0 : undefined}
        className="slot-grid-scroll rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
        style={{ maxHeight: height, overflowY: canScroll ? 'scroll' : 'auto' }}
        onScroll={event => {
          const el = event.currentTarget;
          setAtEnd(el.scrollTop + el.clientHeight >= el.scrollHeight - 2);
        }}
      >
        <div ref={grid} className="relative grid grid-cols-2 gap-2">
          {children}
        </div>
      </div>
      {canScroll && (
        <div className="flex items-center justify-center gap-1.5 pt-2 text-[11px] text-neutral-500">
          {atEnd ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          <span>{atEnd ? 'End of slots · Scroll up for earlier times' : 'More time slots below · Scroll to view'}</span>
        </div>
      )}
    </div>
  );
}

interface ArrivalWindowsSidebarProps {
  clinicSlots: ClinicSlotItem[];
  selectedDate: string;
  isToday: boolean;
  currentTime: Date;
  isOpen?: boolean;
  closedReason?: string;
  closureDetails?: {
    id?: string;
    title: string;
    override_type?: string;
    start_date?: string;
    end_date?: string;
    reason?: string;
    emergency_phone?: string;
  } | null;
  isLoading?: boolean;
  isRefreshing?: boolean;
  onBookSlot: (timeLabel: string) => void;
  onRefresh?: () => void;
  onJumpToDate?: (dateStr: string) => void;
  onManageOverrides?: () => void;
}

export function ArrivalWindowsSidebar({
  clinicSlots,
  selectedDate,
  isToday,
  currentTime,
  isOpen = false,
  closedReason,
  closureDetails,
  isLoading = false,
  isRefreshing = false,
  onBookSlot,
  onRefresh,
  onJumpToDate,
  onManageOverrides,
}: ArrivalWindowsSidebarProps) {
  const [selectedSession, setSelectedSession] = useState<string>('all');
  const [showPastSlots, setShowPastSlots] = useState<boolean>(false);
  const [onlyAvailable, setOnlyAvailable] = useState<boolean>(false);

  const isSlotPast = useCallback((slot: ClinicSlotItem) => {
    if (slot.is_past || slot.window_state === 'PAST') {
      return true;
    }
    if (!isToday) {
      const todayStr = formatDateISO(new Date());
      return selectedDate < todayStr;
    }
    if (slot.start_time && new Date(slot.start_time).getTime() <= currentTime.getTime()) {
      return true;
    }
    if (slot.time_label) {
      const slotMinutes = parseTimeToMinutes(slot.time_label);
      const currentMinutes = currentTime.getHours() * 60 + currentTime.getMinutes();
      if (slotMinutes !== null && slotMinutes <= currentMinutes) {
        return true;
      }
    }
    return false;
  }, [isToday, selectedDate, currentTime]);

  const isSlotBookable = useCallback((slot: ClinicSlotItem) => {
    if (isSlotPast(slot)) return false;
    return Boolean(slot.is_available && slot.status_type === 'AVAILABLE' && slot.window_state !== 'CLOSED');
  }, [isSlotPast]);

  const openCapacity = useMemo(() => {
    if (!isOpen) return 0;
    return clinicSlots.reduce(
      (total, slot) => total + (isSlotBookable(slot) ? 1 : 0),
      0,
    );
  }, [clinicSlots, isOpen, isSlotBookable]);

  const openWindowCount = useMemo(
    () => clinicSlots.filter(isSlotBookable).length,
    [clinicSlots, isSlotBookable],
  );

  const isDayConcluded = useMemo(() => {
    return isToday && clinicSlots.length > 0 && clinicSlots.every(isSlotPast);
  }, [isToday, clinicSlots, isSlotPast]);

  const nextOpenDate = useMemo(() => {
    const base = new Date(selectedDate + 'T00:00:00');
    if (closureDetails?.end_date) {
      const endD = new Date(closureDetails.end_date + 'T00:00:00');
      endD.setDate(endD.getDate() + 1);
      if (endD.getDay() === 0) endD.setDate(endD.getDate() + 1);
      return formatDateISO(endD);
    }
    base.setDate(base.getDate() + 1);
    if (base.getDay() === 0) {
      base.setDate(base.getDate() + 1);
    }
    return formatDateISO(base);
  }, [selectedDate, closureDetails]);

  const nextOpenDateLabel = useMemo(() => {
    const d = new Date(nextOpenDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
  }, [nextOpenDate]);

  const detectedSessions = useMemo(() => {
    const set = new Set<string>();
    clinicSlots.forEach((s) => {
      if (s.session) set.add(s.session);
    });
    return Array.from(set);
  }, [clinicSlots]);

  const operatingHoursSpan = useMemo(() => {
    if (!clinicSlots.length) return '';
    const first = clinicSlots[0];
    const last = clinicSlots[clinicSlots.length - 1];
    return first?.time_label && last?.time_label ? `${first.time_label} – ${last.time_label}` : '';
  }, [clinicSlots]);

  const sessionMetadata = useMemo(() => {
    return detectedSessions.map((sessionId) => {
      const sessionSlots = clinicSlots.filter((s) => s.session === sessionId);
      const openCount = sessionSlots.filter(isSlotBookable).length;
      const firstSlot = sessionSlots[0];
      const lastSlot = sessionSlots[sessionSlots.length - 1];
      const timeSpan = firstSlot && lastSlot ? `${firstSlot.time_label} – ${lastSlot.time_label}` : '';
      const label =
        sessionId === 'morning'
          ? 'Morning'
          : sessionId === 'evening'
            ? 'Evening'
            : sessionId === 'overtime'
              ? 'Overtime'
              : sessionId.charAt(0).toUpperCase() + sessionId.slice(1);

      return {
        id: sessionId,
        label,
        slots: sessionSlots,
        totalCount: sessionSlots.length,
        openCount,
        timeSpan,
      };
    });
  }, [detectedSessions, clinicSlots, isSlotBookable]);

  const nextImmediateSlot = useMemo(() => {
    if (!isOpen) return null;
    return clinicSlots.find(isSlotBookable) || null;
  }, [clinicSlots, isOpen, isSlotBookable]);

  const nextEveningSlot = useMemo(() => {
    if (!isOpen) return null;
    const eveningGroup = clinicSlots.filter((s) => s.session === 'evening');
    if (!eveningGroup.length) return null;
    return eveningGroup.find(isSlotBookable) || null;
  }, [clinicSlots, isOpen, isSlotBookable]);

  const effectiveSession = useMemo(() => {
    if (detectedSessions.length <= 1) {
      return detectedSessions[0] || 'all';
    }
    if (selectedSession !== 'all' && detectedSessions.includes(selectedSession)) {
      return selectedSession;
    }
    if (isToday && currentTime.getHours() >= 14 && detectedSessions.includes('evening')) {
      const eveningMeta = sessionMetadata.find((m) => m.id === 'evening');
      if (eveningMeta && eveningMeta.openCount > 0) {
        return 'evening';
      }
    }
    return 'all';
  }, [detectedSessions, selectedSession, isToday, currentTime, sessionMetadata]);

  const displayedSlots = useMemo(() => {
    let slots = clinicSlots;
    if (effectiveSession !== 'all') {
      slots = slots.filter((s) => s.session === effectiveSession);
    }
    if (onlyAvailable) {
      slots = slots.filter(isSlotBookable);
    }
    return slots;
  }, [clinicSlots, effectiveSession, onlyAvailable, isSlotBookable]);

  const { pastSlots, upcomingSlots } = useMemo(() => {
    const past: ClinicSlotItem[] = [];
    const upcoming: ClinicSlotItem[] = [];
    displayedSlots.forEach((s) => {
      if (isSlotPast(s)) {
        past.push(s);
      } else {
        upcoming.push(s);
      }
    });
    return { pastSlots: past, upcomingSlots: upcoming };
  }, [displayedSlots, isSlotPast]);

  const renderSlotCard = (slot: ClinicSlotItem, index?: number) => {
    const booked = slot.booked_count || 0;
    const past = isSlotPast(slot);
    const isFull = !past && !isSlotBookable(slot);
    const isLimited = !past && !isFull && booked > 0;

    return (
      <div
        key={`${slot.session || 'slot'}-${slot.time_label}-${index ?? 0}`}
        role="button"
        tabIndex={!past && !isFull ? 0 : -1}
        onClick={() => {
          if (!past && !isFull) {
            onBookSlot(slot.time_label);
          }
        }}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !past && !isFull) {
            e.preventDefault();
            onBookSlot(slot.time_label);
          }
        }}
        className={`p-2.5 rounded-xl border text-left flex flex-col justify-between gap-1.5 transition-all outline-none ${past
          ? 'bg-neutral-50/70 border-neutral-200/50 opacity-60 cursor-not-allowed select-none'
          : isFull
            ? 'bg-neutral-50 border-neutral-200 text-neutral-600 cursor-default'
            : isLimited
              ? 'bg-white border-amber-300 hover:border-amber-400 hover:shadow-xs cursor-pointer group focus-visible:ring-2 focus-visible:ring-amber-400'
              : 'bg-white border-neutral-200 hover:border-neutral-900 hover:shadow-xs cursor-pointer group focus-visible:ring-2 focus-visible:ring-neutral-900'
          }`}
      >
        <div className="flex items-center justify-between gap-1">
          <span className="font-mono font-semibold text-[11px] text-neutral-900">
            {slot.time_label}
          </span>
          <span
            className={`text-[9px] font-mono font-medium px-1.5 py-0.2 rounded ${past
              ? 'bg-neutral-100 text-neutral-400'
              : isFull
                ? 'bg-neutral-100 text-neutral-600'
                : isLimited
                  ? 'bg-amber-50 text-amber-900 border border-amber-200'
                  : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
              }`}
          >
            {past ? 'Concluded' : isFull ? 'Unavailable' : isLimited ? 'Busy' : 'Available'}
          </span>
        </div>

        <div className="flex items-center justify-between gap-1 text-[11px] pt-1 border-t border-neutral-100">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[9.5px] text-neutral-500">
              {booked} expected
            </span>
          </div>

          <div>
            {past ? (
              <span className="text-[9.5px] text-neutral-400">Closed</span>
            ) : isFull ? (
              <span className="text-[9.5px] text-neutral-500">Reserved</span>
            ) : (
              <span className="text-[10px] font-medium text-neutral-800 group-hover:text-black flex items-center gap-0.5">
                <Plus className="w-2.5 h-2.5" /> Book
              </span>
            )}
          </div>
        </div>

        {slot.booked_patients && slot.booked_patients.length > 0 && (
          <div className="flex items-center gap-1 overflow-hidden pt-0.5">
            {slot.booked_patients.map((p, idx) => (
              <span
                key={idx}
                className="text-[9.5px] font-medium text-neutral-600 truncate max-w-[70px] bg-neutral-100 px-1 py-0.5 rounded"
              >
                {p.patient_name.split(' ')[0]}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  };

  if (isLoading) return <ArrivalWindowsSkeleton />;

  if (!isOpen) {
    return (
      <div className="bg-white rounded-2xl border border-neutral-200 shadow-2xs p-3.5 flex flex-col h-fit space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <span className="w-2 h-2 rounded-full bg-neutral-400" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 font-mono">
                Non-Operational Day
              </span>
            </div>
            <h2 className="text-xs font-bold text-neutral-950 uppercase tracking-wider">
              Outpatient Schedule
            </h2>
          </div>
          <span className="text-[11px] font-mono font-semibold text-neutral-600 bg-neutral-100 px-2.5 py-0.5 rounded-full border border-neutral-200">
            Closed
          </span>
        </div>

        <div className="p-3.5 rounded-xl bg-neutral-50/80 border border-neutral-200/80 space-y-2.5">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-neutral-900 text-white flex items-center justify-center shrink-0 shadow-xs">
              <DoorClosed className="w-4 h-4 text-neutral-300" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-neutral-950">
                {closureDetails?.title || closedReason || (isToday ? 'Clinic Closed Today' : 'Closed on this Day')}
              </h3>
              <p className="text-[11.5px] text-neutral-500 leading-relaxed mt-0.5">
                {closedReason ||
                  'Configured as a non-working day in clinic weekly operating hours. No appointment slots or walk-in queues are active.'}
              </p>
            </div>
          </div>

          {closureDetails && (
            <div className="p-2 rounded-lg bg-white border border-neutral-200 text-[11px] space-y-1">
              <div className="flex items-center justify-between text-neutral-600 font-mono text-[10px]">
                <span>Closure Duration</span>
                <span className="font-semibold text-neutral-900">
                  {closureDetails.start_date === closureDetails.end_date
                    ? closureDetails.start_date
                    : `${closureDetails.start_date} → ${closureDetails.end_date}`}
                </span>
              </div>
              {closureDetails.reason && (
                <p className="text-neutral-500 text-[10.5px]">
                  <span className="text-neutral-400">Note: </span>
                  {closureDetails.reason}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="p-3 rounded-xl bg-white border border-neutral-200 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-neutral-500 font-medium flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-neutral-400" />
              Next Working Day
            </span>
            <span className="font-mono font-bold text-neutral-900 text-[11px]">
              {nextOpenDateLabel}
            </span>
          </div>
          {onJumpToDate && (
            <button
              type="button"
              onClick={() => onJumpToDate(nextOpenDate)}
              className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-neutral-950 hover:bg-black text-white text-xs font-semibold transition-colors cursor-pointer"
            >
              <span>View {nextOpenDateLabel.split(',')[0]} Schedule</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {onManageOverrides && (
          <button
            type="button"
            onClick={onManageOverrides}
            className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg border border-neutral-200 hover:border-neutral-300 bg-neutral-50 hover:bg-white text-neutral-800 text-xs font-semibold transition-colors cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5 text-neutral-500" />
            <span>Open Special Shift for this Date</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-neutral-200 shadow-2xs p-3.5 flex flex-col h-fit">
      <div className="shrink-0 space-y-2 pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-semibold text-neutral-900 tracking-wide uppercase">
              Appointment Slots
            </h2>
            <span
              className={`text-[10px] font-medium font-mono px-2 py-0.2 rounded-full border ${isDayConcluded
                ? 'bg-neutral-100 text-neutral-600 border-neutral-200'
                : openCapacity > 0
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-neutral-100 text-neutral-600 border-neutral-200'
                }`}
            >
              {isDayConcluded ? 'Closed' : `${openCapacity} spot${openCapacity === 1 ? '' : 's'} open`}
            </span>
          </div>

          <div className="flex items-center gap-1">
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isRefreshing}
                aria-label="Refresh appointment slots"
                title="Refresh appointment slots"
                className="rounded-md border border-neutral-200 bg-white p-1 text-neutral-600 hover:border-neutral-300 hover:text-neutral-900 disabled:cursor-wait disabled:opacity-60"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
              </button>
            )}
            <button
              type="button"
              onClick={() => setOnlyAvailable((prev) => !prev)}
              className={`px-2 py-0.5 rounded-md text-[10.5px] font-medium transition-colors cursor-pointer border shrink-0 ${onlyAvailable
                ? 'bg-neutral-900 text-white border-neutral-900'
                : 'bg-white text-neutral-600 border-neutral-200 hover:border-neutral-300'
                }`}
            >
              {onlyAvailable ? 'Open Only' : 'Filter: Open'}
            </button>
          </div>
        </div>

        {!isDayConcluded && openCapacity > 0 && (
          <p className="text-[10.5px] text-neutral-500">
            {openCapacity} patient place{openCapacity === 1 ? '' : 's'} across {openWindowCount} time window{openWindowCount === 1 ? '' : 's'}.
          </p>
        )}

        {isDayConcluded && (
          <div className="p-3 rounded-xl bg-neutral-50 border border-neutral-200 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-neutral-800">
                <Clock className="w-3.5 h-3.5 text-neutral-500" />
                <span className="text-xs font-semibold text-neutral-900">OPD Concluded for Today</span>
              </div>
              <span className="text-[10px] font-mono text-neutral-500 font-medium px-1.5 py-0.5 rounded bg-neutral-200/70">
                Closed
              </span>
            </div>
            {onJumpToDate && (
              <button
                type="button"
                onClick={() => onJumpToDate(nextOpenDate)}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-medium transition-colors cursor-pointer"
              >
                <span>Check {nextOpenDateLabel.split(',')[0]} Slots</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}

        {!isDayConcluded && nextImmediateSlot && (
          <div className="rounded-xl border border-neutral-200/80 bg-neutral-50/70 p-2.5 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[9.5px] font-medium uppercase tracking-wider text-neutral-600 bg-white border border-neutral-200/90 px-2 py-0.5 rounded-md shadow-2xs">
                Earliest Opening
              </span>
              {operatingHoursSpan && (
                <span className="text-[10px] font-mono font-normal text-neutral-500">
                  {operatingHoursSpan}
                </span>
              )}
            </div>

            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-base font-semibold font-mono tracking-tight text-neutral-900">
                  {nextImmediateSlot.time_label}
                </div>
                <div className="text-[10.5px] font-normal text-neutral-500">
                  {nextImmediateSlot.booked_count || 0} expected arrival{(nextImmediateSlot.booked_count || 0) === 1 ? '' : 's'}
                </div>
              </div>

              <button
                type="button"
                onClick={() => onBookSlot(nextImmediateSlot.time_label)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-neutral-950 hover:bg-black text-white text-xs font-medium shadow-xs active:scale-95 transition-all cursor-pointer"
              >
                <Zap className="w-3 h-3 text-amber-400 fill-amber-400" />
                <span>Book Now</span>
              </button>
            </div>

            {nextEveningSlot &&
              nextEveningSlot.time_label !== nextImmediateSlot.time_label && (
                <div className="pt-1.5 border-t border-neutral-200/70 flex items-center justify-between text-[10.5px]">
                  <span className="text-neutral-500 flex items-center gap-1">
                    <Moon className="w-3 h-3 text-indigo-500" />
                    Evening opening:
                  </span>
                  <button
                    type="button"
                    onClick={() => onBookSlot(nextEveningSlot.time_label)}
                    className="font-mono font-semibold text-neutral-800 hover:text-black underline underline-offset-2 cursor-pointer flex items-center gap-1"
                  >
                    <span>{nextEveningSlot.time_label}</span>
                    <ArrowRight className="w-2.5 h-2.5" />
                  </button>
                </div>
              )}
          </div>
        )}

        {detectedSessions.length > 1 && (
          <div className="p-0.5 bg-neutral-100 rounded-lg flex items-center gap-0.5 border border-neutral-200/80 overflow-x-auto">
            <button
              type="button"
              onClick={() => setSelectedSession('all')}
              className={`flex-1 min-w-[50px] flex items-center justify-center gap-1 py-1 px-1.5 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${effectiveSession === 'all'
                ? 'bg-white text-neutral-950 shadow-2xs'
                : 'text-neutral-500 hover:text-neutral-800'
                }`}
            >
              <Layers className="w-3 h-3 text-neutral-400" />
              <span>All</span>
            </button>

            {sessionMetadata.map((meta) => {
              const isActive = effectiveSession === meta.id;
              const Icon = meta.id === 'morning' ? Sun : meta.id === 'evening' ? Moon : Sparkles;
              return (
                <button
                  key={meta.id}
                  type="button"
                  onClick={() => setSelectedSession(meta.id)}
                  className={`flex-1 min-w-[62px] flex items-center justify-center gap-1 py-1 px-1.5 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${isActive
                    ? 'bg-white text-neutral-950 shadow-2xs'
                    : 'text-neutral-500 hover:text-neutral-800'
                    }`}
                >
                  <Icon
                    className={`w-3 h-3 ${meta.id === 'morning'
                      ? 'text-amber-500'
                      : meta.id === 'evening'
                        ? 'text-indigo-500'
                        : 'text-neutral-400'
                      }`}
                  />
                  <span>{meta.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="min-h-0 space-y-2">
        {pastSlots.length > 0 && !onlyAvailable && (
          <div className="rounded-lg border border-neutral-200/70 bg-neutral-50/80 overflow-hidden">
            <button
              type="button"
              onClick={() => setShowPastSlots((prev) => !prev)}
              className="w-full flex items-center justify-between px-2.5 py-1.5 text-left text-neutral-600 hover:text-neutral-900 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-1.5 text-[10.5px] font-medium">
                <Clock className="w-3 h-3 text-neutral-400" />
                <span>
                  {pastSlots.length} past slot{pastSlots.length === 1 ? '' : 's'} earlier today
                </span>
              </div>
              <div className="flex items-center gap-1 text-[10px] font-mono text-neutral-500">
                <span>{showPastSlots ? 'Hide' : 'Review'}</span>
                {showPastSlots ? (
                  <ChevronUp className="w-3 h-3 text-neutral-400" />
                ) : (
                  <ChevronDown className="w-3 h-3 text-neutral-400" />
                )}
              </div>
            </button>

            {showPastSlots && (
              <div className="p-2 border-t border-neutral-200/70 bg-white/60 space-y-2">
                <SlotGrid>
                  {pastSlots.map((slot, idx) => renderSlotCard(slot, idx))}
                </SlotGrid>
                {upcomingSlots.length > 0 && (
                  <div className="text-[9.5px] font-mono uppercase tracking-wider text-neutral-400 font-semibold pt-1 border-t border-neutral-100">
                    Upcoming Slots
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {upcomingSlots.length > 0 ? (
          <SlotGrid>
            {upcomingSlots.map((slot, idx) => renderSlotCard(slot, idx))}
          </SlotGrid>
        ) : pastSlots.length > 0 && !showPastSlots ? (
          <div className="p-4 text-center text-xs text-neutral-500 bg-neutral-50 rounded-xl border border-neutral-200/80 space-y-1">
            <p className="font-semibold text-neutral-800">All displayed slots have concluded</p>
            <p className="text-[11px] text-neutral-400">
              Click &quot;Review&quot; above to inspect earlier patient appointments.
            </p>
          </div>
        ) : displayedSlots.length === 0 ? (
          <div className="p-6 text-center text-xs text-neutral-400 border border-dashed border-neutral-200 rounded-xl">
            {onlyAvailable
              ? 'No open slots matching your filter'
              : 'No appointment slots configured for this view'}
          </div>
        ) : null}
      </div>
    </div>
  );
}
