'use client';

import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  Loader2,
  UserCheck,
  Stethoscope,
  FlaskConical,
  CalendarClock,
  Clock,
} from 'lucide-react';
import { AppointmentItem } from '../../types';
import { useClinicStore } from '../../store';

interface ChamberBannerProps {
  isToday: boolean;
  currentInChamber: AppointmentItem | null;
  nextUpPatient: AppointmentItem | null;
  actionState: { id: string; action: 'arrive' | 'call' | 'complete' | 'skip' | 'reinsert' | 'move_tomorrow' } | null;
  onComplete: (id: string) => void;
  onSkip: (id: string) => void;
  onMoveTomorrow: (id: string) => void;
  onCallNext: (id: string) => void;
}

export function ChamberBanner({
  isToday,
  currentInChamber,
  nextUpPatient,
  actionState,
  onComplete,
  onSkip,
  onMoveTomorrow,
  onCallNext,
}: ChamberBannerProps) {
  const activeRole = useClinicStore((s) => s.activeRole);
  const isDoctor = activeRole === 'doctor';
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  const chamberVisitId = currentInChamber?.id;
  const consultationStartedAt = currentInChamber?.consultation_started_at;

  useEffect(() => {
    if (!chamberVisitId) {
      setElapsedSeconds(0);
      return;
    }

    const startTime = consultationStartedAt
      ? new Date(consultationStartedAt).getTime()
      : Date.now();

    const calculateElapsed = () => {
      const diff = Math.max(0, Math.floor((Date.now() - startTime) / 1000));
      setElapsedSeconds(diff);
    };

    calculateElapsed();
    const interval = setInterval(calculateElapsed, 1000);
    return () => clearInterval(interval);
  }, [chamberVisitId, consultationStartedAt]);

  if (!isToday) return null;

  const formatDuration = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  if (currentInChamber) {
    const isActingOnCurrent = actionState?.id === currentInChamber.id;

    return (
      <div className="relative overflow-hidden bg-white border border-neutral-300 rounded-2xl p-4 sm:p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-start sm:items-center gap-3.5 min-w-0">
            <div className="w-12 h-12 rounded-xl bg-neutral-950 text-white font-mono font-bold text-base flex items-center justify-center shrink-0 shadow-sm border border-neutral-800">
              {currentInChamber.display_token || 'DOC'}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-800 bg-emerald-50 border border-emerald-200/80 px-2 py-0.5 rounded-md">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  In Consultation
                </span>
                <div className="inline-flex items-center gap-1 text-[11px] font-mono font-semibold text-neutral-600 bg-neutral-100 border border-neutral-200 px-2 py-0.5 rounded-md">
                  <Clock className="w-3 h-3 text-neutral-500" />
                  {formatDuration(elapsedSeconds)}
                </div>
                <span className="text-[11px] text-neutral-500 font-medium">
                  {currentInChamber.source === 'walk_in' ? 'Walk-in' : `Scheduled • ${currentInChamber.appointment_time || ''}`}
                </span>
                {currentInChamber.call_count && currentInChamber.call_count > 1 ? (
                  <span className="text-[10px] text-neutral-700 bg-neutral-100 border border-neutral-200 px-1.5 py-0.5 rounded font-mono">
                    Recall {currentInChamber.call_count}×
                  </span>
                ) : null}
              </div>
              <h3 className="text-[15px] font-bold text-neutral-950 mt-1 truncate">
                {currentInChamber.patient_name}
                <span className="font-mono text-xs font-normal text-neutral-500 ml-2">
                  {currentInChamber.patient_phone}
                </span>
              </h3>
              <p className="text-xs text-neutral-500 mt-0.5 truncate">
                {currentInChamber.chief_complaint || 'General Consultation'}
              </p>
            </div>
          </div>

          {isDoctor ? (
            <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-neutral-100">
              <button
                type="button"
                disabled={isActingOnCurrent}
                onClick={() => onComplete(currentInChamber.id)}
                className="h-9 px-3.5 rounded-xl bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-xs disabled:opacity-50"
              >
                {isActingOnCurrent && actionState.action === 'complete' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                )}
                <span>End Visit</span>
              </button>

              <button
                type="button"
                disabled={isActingOnCurrent}
                onClick={() => onSkip(currentInChamber.id)}
                className="h-9 px-3 rounded-xl border border-amber-200 bg-amber-50 hover:bg-amber-100/80 text-amber-900 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
              >
                {isActingOnCurrent && actionState.action === 'skip' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-700" />
                ) : (
                  <FlaskConical className="w-3.5 h-3.5 text-amber-700" />
                )}
                <span>Step Out for Lab</span>
              </button>

              <button
                type="button"
                disabled={isActingOnCurrent}
                onClick={() => onMoveTomorrow(currentInChamber.id)}
                className="h-9 px-3 rounded-xl border border-neutral-200 bg-white hover:bg-neutral-50 text-neutral-700 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
              >
                {isActingOnCurrent && actionState.action === 'move_tomorrow' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-500" />
                ) : (
                  <CalendarClock className="w-3.5 h-3.5 text-neutral-500" />
                )}
                <span>Come Back Tomorrow</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-neutral-100">
              <span className="px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs font-semibold">
                In Chamber
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (nextUpPatient) {
    const isActingOnNext = actionState?.id === nextUpPatient.id;

    return (
      <div className="bg-white border border-neutral-200/90 rounded-2xl p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-neutral-100 border border-neutral-200 text-neutral-700 flex items-center justify-center shrink-0">
            <Stethoscope className="w-4 h-4 text-neutral-800" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
                Next in Queue
              </span>
              <span className="font-mono text-xs font-bold text-neutral-950">
                {nextUpPatient.display_token}
              </span>
            </div>
            <p className="text-xs font-semibold text-neutral-900 truncate mt-0.5">
              {nextUpPatient.patient_name}
              <span className="font-normal text-neutral-500 ml-1.5">
                ({nextUpPatient.source === 'walk_in' ? 'Walk-in' : nextUpPatient.appointment_time || 'Scheduled'})
              </span>
            </p>
          </div>
        </div>

        {isDoctor ? (
          <button
            type="button"
            disabled={isActingOnNext}
            onClick={() => onCallNext(nextUpPatient.id)}
            className="h-8 px-4 rounded-xl bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold flex items-center gap-1.5 transition-all shadow-xs cursor-pointer active:scale-95"
          >
            {isActingOnNext && actionState.action === 'call' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <UserCheck className="w-3.5 h-3.5 text-white" />
            )}
            <span>Call Patient In</span>
          </button>
        ) : (
          <span className="px-3 py-1.5 rounded-xl bg-neutral-100 border border-neutral-200 text-neutral-600 text-xs font-semibold">
            Waiting in Queue
          </span>
        )}
      </div>
    );
  }

  return null;
}
