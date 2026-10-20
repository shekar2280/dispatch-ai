'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { CallRecordingPlayer, type ConversationTurn } from './CallRecordingPlayer';
import {
  Play,
  Pause,
  Sparkles,
  PhoneCall,
  ShieldAlert,
  Bot,
  Clock,
  ChevronDown,
  Copy,
  Check,
  CheckCircle2,
  FileText,
  PhoneIncoming,
  PhoneMissed,
} from 'lucide-react';

interface CallSession {
  id: string;
  caller_phone: string;
  caller_name: string;
  patient_id?: string | null;
  patient_name?: string | null;
  start_time: string;
  duration_seconds: number;
  triage_status: string;
  call_outcome: string;
  missed_reason?: string | null;
  handled_by: string;
  is_missed?: boolean;
  summary: string;
  full_transcript?: string | null;
  total_turns?: number;
  turns?: ConversationTurn[];
  recording_status?: 'disabled' | 'processing' | 'ready' | 'failed' | string | null;
  audio_recording_url?: string | null;
}

interface CallRecordCardProps {
  call: CallSession;
  isExpanded: boolean;
  isPlaying: boolean;
  copiedId: string | null;
  onToggleExpand: () => void;
  onTogglePlay: (e: React.MouseEvent, id: string, audioUrl?: string | null) => void;
  onCopy: (e: React.MouseEvent, id: string, text: string) => void;
  formatTime: (iso: string) => string;
  formatDate: (iso: string) => string;
  formatDuration: (seconds: number) => string;
  isMissedCall: (call: CallSession) => boolean;
}

export function CallRecordCard({
  call,
  isExpanded,
  isPlaying,
  copiedId,
  onToggleExpand,
  onTogglePlay,
  onCopy,
  formatTime,
  formatDate,
  formatDuration,
  isMissedCall,
}: CallRecordCardProps) {
  const router = useRouter();
  const matchedPatient = call.patient_id ? { id: call.patient_id } : null;
  const isMissed = isMissedCall(call);
  const isEmergency = call.triage_status === 'EMERGENCY' || call.call_outcome === 'emergency_deflected';
  const isBooked = call.call_outcome === 'appointment_booked' || call.triage_status === 'APPOINTMENT' || Boolean(call.summary?.includes('Appointment booked'));

  const missedReason = ({
    caller_silent: 'No speech detected',
    speech_unrecognized: 'Couldn’t hear caller',
    caller_abandoned: 'Ended before answer',
    no_answer: 'No answer',
    line_busy: 'Line busy',
    service_unavailable: 'Unavailable',
    ringing: 'Ringing timeout',
  } as Record<string, string>)[call.call_outcome] || 'Not answered';

  return (
    <div
      onClick={onToggleExpand}
      className={`group transition-colors duration-150 cursor-pointer ${
        isExpanded
          ? 'bg-neutral-50/90'
          : isMissed
          ? 'bg-white hover:bg-rose-50/30'
          : isEmergency
          ? 'bg-white hover:bg-rose-50/30'
          : isBooked
          ? 'bg-white hover:bg-emerald-50/20'
          : 'bg-white hover:bg-neutral-50/80'
      }`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 px-4 py-2.5">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-transform ${
              isMissed
                ? 'bg-rose-100 text-rose-700'
                : isEmergency
                ? 'bg-rose-100 text-rose-700'
                : isBooked
                ? 'bg-emerald-100 text-emerald-800'
                : 'bg-neutral-100 text-neutral-700'
            }`}
          >
            {isMissed ? (
              <PhoneMissed className="w-3.5 h-3.5" />
            ) : isEmergency ? (
              <ShieldAlert className="w-3.5 h-3.5" />
            ) : isBooked ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <PhoneIncoming className="w-3.5 h-3.5" />
            )}
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 min-w-0">
            <span className="truncate text-xs font-semibold text-neutral-900 group-hover:text-emerald-950">
              {call.caller_name || 'Unknown Caller'}
            </span>

            <span className="text-xs font-mono text-neutral-500 tabular-nums">
              {call.caller_phone}
            </span>

            {call.patient_name && call.patient_name.trim().toLowerCase() !== call.caller_name?.trim().toLowerCase() && (
              <span className="hidden md:inline text-[11px] text-neutral-400 truncate">
                for {call.patient_name}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
          <div className="flex items-center gap-2 text-[11px] text-neutral-500 font-mono">
            <span className="flex items-center gap-1 text-neutral-600">
              <Clock className="w-3 h-3 text-neutral-400" />
              {formatTime(call.start_time)}
            </span>
            <span className="text-neutral-300">·</span>
            <span className={isMissed ? 'text-rose-600 font-medium' : 'text-neutral-700 font-medium'}>
              {call.duration_seconds > 0 ? formatDuration(call.duration_seconds) : '0s'}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            {isMissed ? (
              <span className="px-2 py-0.5 rounded-md bg-rose-50 border border-rose-200/80 text-[10px] font-mono font-semibold text-rose-700">
                Missed
              </span>
            ) : isEmergency ? (
              <span className="px-2 py-0.5 rounded-md bg-rose-50 border border-rose-200/80 text-[10px] font-mono font-semibold text-rose-700">
                Emergency
              </span>
            ) : isBooked ? (
              <span className="px-2 py-0.5 rounded-md bg-emerald-50 border border-emerald-200/80 text-[10px] font-mono font-semibold text-emerald-800">
                Booked
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-md bg-neutral-100 border border-neutral-200/80 text-[10px] font-mono font-medium text-neutral-700">
                Answered
              </span>
            )}
          </div>

          <div className="flex items-center gap-1">
            {call.audio_recording_url && (
              <button
                type="button"
                onClick={(e) => onTogglePlay(e, call.id, call.audio_recording_url)}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border transition-colors ${
                  isPlaying
                    ? 'bg-neutral-900 text-white border-neutral-900'
                    : 'bg-white text-neutral-700 hover:bg-neutral-100 border-neutral-200'
                }`}
              >
                {isPlaying ? <Pause className="w-2.5 h-2.5" /> : <Play className="w-2.5 h-2.5" />}
                <span className="hidden sm:inline">{isPlaying ? 'Playing' : 'Audio'}</span>
              </button>
            )}

            {matchedPatient && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  router.push(`/clinic/patients?id=${matchedPatient.id}`);
                }}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-neutral-200 bg-white hover:bg-neutral-100 text-[10px] font-medium text-neutral-700 transition-colors"
                title="View Patient Record"
              >
                <FileText className="w-2.5 h-2.5 text-neutral-400" />
                <span>Record</span>
              </button>
            )}

            <button
              type="button"
              aria-label="Toggle details"
              className="p-1 rounded-md text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100"
            >
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform duration-200 ${
                  isExpanded ? 'rotate-180 text-neutral-900' : ''
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 pt-2 border-t border-neutral-200/70 space-y-3 bg-neutral-50/60">
          <CallRecordingPlayer
            callId={call.id}
            recordingStatus={call.recording_status}
            turns={call.turns}
            transcript={call.full_transcript}
          />

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-xs">
            <div className="p-2.5 rounded-lg bg-white border border-neutral-200/70">
              <span className="text-[10px] uppercase font-mono font-semibold text-neutral-400 block">
                Timestamp
              </span>
              <span className="font-medium text-neutral-800 mt-0.5 block truncate">
                {formatDate(call.start_time)} {formatTime(call.start_time)}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-white border border-neutral-200/70">
              <span className="text-[10px] uppercase font-mono font-semibold text-neutral-400 block">
                Duration
              </span>
              <span className="font-mono font-medium text-neutral-800 mt-0.5 block">
                {call.duration_seconds > 0 ? formatDuration(call.duration_seconds) : 'No speech'}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-white border border-neutral-200/70">
              <span className="text-[10px] uppercase font-mono font-semibold text-neutral-400 block">
                Handler
              </span>
              <span className="font-medium text-neutral-800 mt-0.5 block truncate">
                {isMissed ? missedReason : call.handled_by || 'AI Receptionist'}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-white border border-neutral-200/70">
              <span className="text-[10px] uppercase font-mono font-semibold text-neutral-400 block">
                Result
              </span>
              <span className="font-medium text-neutral-800 mt-0.5 block truncate">
                {isMissed ? 'Missed Call' : isEmergency ? 'Emergency' : isBooked ? 'Appointment Booked' : 'General Inquiry'}
              </span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-white border border-neutral-200/80 space-y-1">
            <p className="text-[10px] font-mono font-semibold text-neutral-500 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles className="w-3 h-3 text-neutral-400" />
              {isMissed ? 'Call Reason' : 'Call Summary'}
            </p>
            <p className="text-xs leading-relaxed text-neutral-800 whitespace-pre-line">
              {(isMissed ? missedReason : call.summary) || 'No transcript recorded for this session.'}
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="flex items-center gap-2">
              {call.audio_recording_url && (
                <button
                  type="button"
                  onClick={(e) => onTogglePlay(e, call.id, call.audio_recording_url)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                    isPlaying
                      ? 'bg-neutral-900 text-white border-neutral-900'
                      : 'bg-white text-neutral-800 hover:bg-neutral-100 border-neutral-200 shadow-2xs'
                  }`}
                >
                  {isPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                  <span>{isPlaying ? 'Pause Audio' : 'Play Recording'}</span>
                </button>
              )}

              <a
                href={`tel:${call.caller_phone}`}
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white text-neutral-800 hover:bg-neutral-100 border border-neutral-200 shadow-2xs transition-all"
              >
                <PhoneCall className="w-3 h-3 text-neutral-600" />
                <span>Call Back</span>
              </a>

              <button
                type="button"
                onClick={(e) => onCopy(e, call.id, call.caller_phone)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white text-neutral-700 hover:bg-neutral-100 border border-neutral-200 shadow-2xs transition-all"
              >
                {copiedId === call.id ? (
                  <>
                    <Check className="w-3 h-3 text-emerald-600" />
                    <span className="text-emerald-700">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3 h-3 text-neutral-400" />
                    <span>Copy Phone</span>
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (matchedPatient) {
                    router.push(`/clinic/patients?id=${matchedPatient.id}`);
                  } else {
                    router.push(`/clinic/patients?phone=${encodeURIComponent(call.caller_phone)}&name=${encodeURIComponent(call.caller_name || '')}`);
                  }
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-neutral-900 text-white hover:bg-black border border-neutral-900 shadow-2xs transition-all"
              >
                <FileText className="w-3 h-3 text-neutral-300" />
                <span>{matchedPatient ? 'See Patient Record' : 'Search Directory'}</span>
              </button>
            </div>

            <span className="text-[10px] font-mono text-neutral-400">
              ID: {call.id.slice(0, 8)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
