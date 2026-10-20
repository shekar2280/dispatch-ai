'use client';

import React from 'react';
import {
  X,
  Clock,
  Calendar,
  CheckCircle2,
  Stethoscope,
  LogIn,
  AlertCircle,
  ShieldCheck,
  RotateCcw,
  Activity,
  ArrowRight,
  UserCheck,
  CalendarClock,
  Sparkles,
} from 'lucide-react';
import { AppointmentItem, VisitEventItem } from '../../types';
import { useClinicStore } from '../../store';
import { useAppointmentEventsQuery } from '../../_hooks/useClinicQueries';
import { formatClinicTime } from '../_utils/timeUtils';

interface AuditTimelineModalProps {
  isOpen: boolean;
  appointment: AppointmentItem | null;
  onClose: () => void;
  clinicTz: string;
}

export function AuditTimelineModal({
  isOpen,
  appointment,
  onClose,
  clinicTz,
}: AuditTimelineModalProps) {
  const orgId = useClinicStore((s) => s.orgId);
  const { data: events, isLoading: isEventsLoading } = useAppointmentEventsQuery(
    isOpen ? appointment?.id : null,
    orgId
  );

  if (!isOpen || !appointment) return null;

  const formatDate = (isoStr?: string | null) => {
    if (!isoStr) return null;
    const d = new Date(isoStr);
    return d.toLocaleString('en-IN', {
      timeZone: clinicTz,
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getPunctuality = () => {
    if (!appointment.appointment_time || !appointment.checked_in_at) return null;
    const match = appointment.appointment_time.match(/(\d+):(\d+)\s*(AM|PM)/i);
    if (!match) return null;
    let hours = parseInt(match[1], 10);
    const mins = parseInt(match[2], 10);
    const ampm = match[3].toUpperCase();
    if (ampm === 'PM' && hours !== 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;
    const slotMins = hours * 60 + mins;

    const checkInDate = new Date(appointment.checked_in_at);
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: clinicTz,
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
    });
    const parts = formatter.formatToParts(checkInDate);
    let ch = 0;
    let cm = 0;
    for (const part of parts) {
      if (part.type === 'hour') ch = parseInt(part.value, 10);
      if (part.type === 'minute') cm = parseInt(part.value, 10);
    }
    const checkInMins = ch * 60 + cm;
    const diff = checkInMins - slotMins;

    if (diff > 20) {
      const h = Math.floor(diff / 60);
      const m = diff % 60;
      return {
        text: h > 0 ? `Late by ${h}h ${m > 0 ? `${m}m` : ''}` : `Late by ${m}m`,
        color: 'text-amber-800 bg-amber-50 border-amber-200',
      };
    }
    if (diff < -20) {
      const earlyM = Math.abs(diff);
      const h = Math.floor(earlyM / 60);
      const m = earlyM % 60;
      return {
        text: h > 0 ? `Early by ${h}h ${m > 0 ? `${m}m` : ''}` : `Early by ${m}m`,
        color: 'text-sky-800 bg-sky-50 border-sky-200',
      };
    }
    return {
      text: 'On Time Check-in',
      color: 'text-emerald-800 bg-emerald-50 border-emerald-200',
    };
  };

  const punctuality = getPunctuality();

  const getEventBadge = (eventType: string) => {
    switch (eventType) {
      case 'WALK_IN_REGISTERED':
        return {
          icon: UserCheck,
          label: 'Walk-In Registered',
          border: 'border-indigo-500/30',
          bg: 'bg-indigo-50/80',
          text: 'text-indigo-800',
          iconColor: 'text-indigo-600',
        };
      case 'APPOINTMENT_BOOKED':
        return {
          icon: Calendar,
          label: 'Appointment Booked',
          border: 'border-blue-500/30',
          bg: 'bg-blue-50/80',
          text: 'text-blue-800',
          iconColor: 'text-blue-600',
        };
      case 'CHECKED_IN':
        return {
          icon: LogIn,
          label: 'Checked In',
          border: 'border-emerald-500/30',
          bg: 'bg-emerald-50/80',
          text: 'text-emerald-800',
          iconColor: 'text-emerald-600',
        };
      case 'CALLED_IN':
        return {
          icon: Stethoscope,
          label: 'Called In',
          border: 'border-amber-500/30',
          bg: 'bg-amber-50/80',
          text: 'text-amber-800',
          iconColor: 'text-amber-600',
        };
      case 'CONSULTATION_STARTED':
        return {
          icon: Activity,
          label: 'Consultation Started',
          border: 'border-amber-600/40',
          bg: 'bg-amber-100/70',
          text: 'text-amber-900',
          iconColor: 'text-amber-700',
        };
      case 'CONSULTATION_ENDED':
        return {
          icon: CheckCircle2,
          label: 'Consultation Complete',
          border: 'border-emerald-500/30',
          bg: 'bg-emerald-50/80',
          text: 'text-emerald-800',
          iconColor: 'text-emerald-600',
        };
      case 'SKIPPED':
        return {
          icon: RotateCcw,
          label: 'Patient Stepped Out',
          border: 'border-rose-400/30',
          bg: 'bg-rose-50/80',
          text: 'text-rose-800',
          iconColor: 'text-rose-600',
        };
      case 'REINSERTED':
        return {
          icon: ArrowRight,
          label: 'Queue Reinserted',
          border: 'border-purple-400/30',
          bg: 'bg-purple-50/80',
          text: 'text-purple-800',
          iconColor: 'text-purple-600',
        };
      case 'RESCHEDULED':
        return {
          icon: CalendarClock,
          label: 'Appointment Rescheduled',
          border: 'border-orange-400/30',
          bg: 'bg-orange-50/80',
          text: 'text-orange-800',
          iconColor: 'text-orange-600',
        };
      case 'CANCELLED':
        return {
          icon: AlertCircle,
          label: 'Appointment Cancelled',
          border: 'border-rose-500/30',
          bg: 'bg-rose-50/80',
          text: 'text-rose-800',
          iconColor: 'text-rose-600',
        };
      default:
        return {
          icon: Clock,
          label: eventType.replace(/_/g, ' '),
          border: 'border-neutral-300',
          bg: 'bg-neutral-50',
          text: 'text-neutral-800',
          iconColor: 'text-neutral-600',
        };
    }
  };

  const hasEvents = Boolean(events && events.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-neutral-950/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="fixed inset-0" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-white rounded-2xl shadow-2xl border border-neutral-200/80 overflow-hidden flex flex-col z-10 max-h-[90vh]">
        <div className="px-6 py-4 border-b border-neutral-200/80 flex items-center justify-between bg-neutral-50/60 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-neutral-900 text-white flex items-center justify-center shadow-xs">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-neutral-900">Visit History &amp; Notes</h2>
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-full bg-neutral-200/70 text-neutral-700 font-semibold">
                  {hasEvents ? `${events?.length} Events` : 'Milestones'}
                </span>
              </div>
              <p className="text-[11px] text-neutral-500">Patient visit timeline and call records</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-neutral-200/80 text-neutral-500 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto space-y-6">
          <div className="p-4 bg-gradient-to-r from-neutral-50 to-neutral-100/60 rounded-xl border border-neutral-200/80 flex items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-neutral-900 text-sm">{appointment.patient_name}</span>
                <span className="font-mono text-xs text-neutral-500">({appointment.patient_phone})</span>
              </div>
              <p className="text-xs text-neutral-600 mt-1">
                Chief Complaint: <span className="font-medium text-neutral-900">{appointment.chief_complaint || 'General Consultation'}</span>
              </p>
            </div>
            <div className="text-right">
              <span className="inline-block px-2.5 py-1 rounded-lg font-mono font-bold text-xs bg-amber-50 text-amber-900 border border-amber-200 shadow-2xs">
                {appointment.display_token || 'No Token'}
              </span>
              <p className="text-[10px] text-neutral-500 font-mono mt-1 uppercase tracking-wider">{appointment.status}</p>
            </div>
          </div>

          {isEventsLoading ? (
            <div className="py-12 flex flex-col items-center justify-center space-y-3">
              <div className="w-6 h-6 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
              <p className="text-xs text-neutral-500 font-mono">Loading visit records...</p>
            </div>
          ) : hasEvents ? (
            <div className="relative pl-6 space-y-5 border-l-2 border-neutral-200 ml-3">
              {events?.map((evt: VisitEventItem, idx: number) => {
                const badge = getEventBadge(evt.event_type);
                const Icon = badge.icon;
                const prevEvt = idx > 0 ? events[idx - 1] : null;
                const elapsedMins = prevEvt
                  ? Math.max(0, Math.round((new Date(evt.occurred_at).getTime() - new Date(prevEvt.occurred_at).getTime()) / 60000))
                  : null;

                return (
                  <div key={evt.id} className="relative group">
                    <div
                      className={`absolute -left-[31px] top-0.5 w-5 h-5 rounded-full ${badge.bg} border-2 ${badge.border} flex items-center justify-center shadow-2xs`}
                    >
                      <Icon className={`w-2.5 h-2.5 ${badge.iconColor}`} />
                    </div>

                    <div className="bg-white p-3 rounded-xl border border-neutral-200/70 hover:border-neutral-300 transition-colors shadow-2xs">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${badge.border} ${badge.bg} ${badge.text}`}>
                            {badge.label}
                          </span>
                          {elapsedMins !== null && elapsedMins > 0 && (
                            <span className="font-mono text-[9px] text-neutral-400 bg-neutral-50 px-1.5 py-0.5 rounded border border-neutral-200/60">
                              +{elapsedMins}m
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[11px] text-neutral-500 font-medium">
                          {formatClinicTime(evt.occurred_at, clinicTz)}
                        </span>
                      </div>

                      {evt.notes && (
                        <p className="text-xs text-neutral-700 mt-2 font-medium">
                          {evt.notes}
                        </p>
                      )}

                      <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-400">
                        <span>Updated by: {evt.actor_type === 'ai_voice' || evt.actor_type === 'tulsi' ? 'Tulsi' : evt.actor_type || 'Staff'}</span>
                        <span className="font-mono">{formatDate(evt.occurred_at)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="relative pl-6 space-y-6 border-l-2 border-neutral-200 ml-3">
              <div className="relative">
                <div className="absolute -left-[31px] top-0.5 w-5 h-5 rounded-full bg-indigo-50 border-2 border-indigo-600 flex items-center justify-center">
                  <Calendar className="w-2.5 h-2.5 text-indigo-600" />
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-700">1. Booking Request</span>
                  <p className="text-xs font-semibold text-neutral-900 mt-0.5">
                    {formatDate(appointment.created_at) || 'Booking initiated'}
                  </p>
                  <p className="text-[11px] text-neutral-500">
                    Channel: {appointment.source === 'ai_voice' ? 'Phone Call (Tulsi)' : appointment.source === 'walk_in' ? 'Walk-in Desk' : 'Front Desk Manual'}
                  </p>
                </div>
              </div>

              <div className="relative">
                <div className="absolute -left-[31px] top-0.5 w-5 h-5 rounded-full bg-neutral-100 border-2 border-neutral-400 flex items-center justify-center">
                  <Clock className="w-2.5 h-2.5 text-neutral-600" />
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-600">2. Scheduled Target</span>
                  <p className="text-xs font-semibold text-neutral-900 mt-0.5">
                    {appointment.appointment_date || 'Today'} • {appointment.appointment_time || 'Walk-in immediate'}
                  </p>
                  <p className="text-[11px] text-neutral-500">Assigned time slot in clinic schedule</p>
                </div>
              </div>

              <div className="relative">
                <div className={`absolute -left-[31px] top-0.5 w-5 h-5 rounded-full flex items-center justify-center ${
                  appointment.checked_in_at ? 'bg-emerald-50 border-2 border-emerald-600' : 'bg-neutral-100 border-2 border-neutral-300'
                }`}>
                  <LogIn className={`w-2.5 h-2.5 ${appointment.checked_in_at ? 'text-emerald-600' : 'text-neutral-400'}`} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-bold uppercase tracking-wider ${
                      appointment.checked_in_at ? 'text-emerald-700' : 'text-neutral-400'
                    }`}>3. Patient Arrived</span>
                    {punctuality && (
                      <span className={`text-[9px] font-bold px-1.5 py-0.2 rounded border ${punctuality.color}`}>
                        {punctuality.text}
                      </span>
                    )}
                  </div>
                  {appointment.checked_in_at ? (
                    <>
                      <p className="text-xs font-semibold text-neutral-900 mt-0.5">
                        {formatDate(appointment.checked_in_at)}
                      </p>
                      <p className="text-[11px] text-neutral-500">Patient physically verified at reception desk</p>
                    </>
                  ) : (
                    <p className="text-xs text-neutral-400 italic mt-0.5">Patient has not yet checked in at desk</p>
                  )}
                </div>
              </div>

              <div className="relative">
                <div className={`absolute -left-[31px] top-0.5 w-5 h-5 rounded-full flex items-center justify-center ${
                  appointment.consultation_started_at ? 'bg-amber-50 border-2 border-amber-600' : 'bg-neutral-100 border-2 border-neutral-300'
                }`}>
                  <Stethoscope className={`w-2.5 h-2.5 ${appointment.consultation_started_at ? 'text-amber-600' : 'text-neutral-400'}`} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-bold uppercase tracking-wider ${
                      appointment.consultation_started_at ? 'text-amber-700' : 'text-neutral-400'
                    }`}>4. Doctor Chamber Entry</span>
                    {appointment.call_count && appointment.call_count > 1 ? (
                      <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                        Called {appointment.call_count}×
                      </span>
                    ) : null}
                  </div>
                  {appointment.consultation_started_at ? (
                    <>
                      <p className="text-xs font-semibold text-neutral-900 mt-0.5">
                        {formatDate(appointment.consultation_started_at)}
                      </p>
                      <p className="text-[11px] text-neutral-500">Called inside doctor consultation room</p>
                    </>
                  ) : (
                    <p className="text-xs text-neutral-400 italic mt-0.5">Waiting for chamber call</p>
                  )}
                </div>
              </div>

              <div className="relative">
                <div className={`absolute -left-[31px] top-0.5 w-5 h-5 rounded-full flex items-center justify-center ${
                  appointment.consultation_ended_at ? 'bg-emerald-50 border-2 border-emerald-600' : 'bg-neutral-100 border-2 border-neutral-300'
                }`}>
                  <CheckCircle2 className={`w-2.5 h-2.5 ${appointment.consultation_ended_at ? 'text-emerald-600' : 'text-neutral-400'}`} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-bold uppercase tracking-wider ${
                      appointment.consultation_ended_at ? 'text-emerald-700' : 'text-neutral-400'
                    }`}>5. Chamber Exit / Completion</span>
                    {Boolean(appointment.actual_duration_seconds) && (
                      <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200">
                        Duration: {Math.max(1, Math.round((appointment.actual_duration_seconds || 0) / 60))}m
                      </span>
                    )}
                  </div>
                  {appointment.consultation_ended_at ? (
                    <>
                      <p className="text-xs font-semibold text-neutral-900 mt-0.5">
                        {formatDate(appointment.consultation_ended_at)}
                      </p>
                      <p className="text-[11px] text-neutral-500">Visit finalized by attending physician</p>
                    </>
                  ) : (
                    <p className="text-xs text-neutral-400 italic mt-0.5">Consultation in progress or pending</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-3.5 border-t border-neutral-200/80 bg-neutral-50/80 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-neutral-900 hover:bg-black text-white text-xs font-bold transition-all shadow-xs cursor-pointer"
          >
            Close Timeline
          </button>
        </div>
      </div>
    </div>
  );
}
