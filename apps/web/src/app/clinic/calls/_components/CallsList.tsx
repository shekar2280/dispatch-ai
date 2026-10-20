'use client';

import React from 'react';
import { Phone } from 'lucide-react';
import { CallRecordCard } from './CallRecordCard';

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
  handled_by: string;
  is_missed?: boolean;
  summary: string;
  audio_recording_url?: string | null;
}

interface CallGroup {
  dateLabel: string;
  items: CallSession[];
}

interface CallsListProps {
  groups: CallGroup[];
  searchQuery: string;
  expandedId: string | null;
  activePlayingId: string | null;
  copiedId: string | null;
  onToggleExpand: (id: string) => void;
  onTogglePlay: (e: React.MouseEvent, id: string, audioUrl?: string | null) => void;
  onCopy: (e: React.MouseEvent, id: string, text: string) => void;
  formatTime: (iso: string) => string;
  formatDate: (iso: string) => string;
  formatDuration: (seconds: number) => string;
  isMissedCall: (call: CallSession) => boolean;
}

export function CallsList({
  groups,
  searchQuery,
  expandedId,
  activePlayingId,
  copiedId,
  onToggleExpand,
  onTogglePlay,
  onCopy,
  formatTime,
  formatDate,
  formatDuration,
  isMissedCall,
}: CallsListProps) {
  if (groups.length === 0) {
    return (
      <div className="py-16 border border-neutral-200/80 rounded-xl bg-white text-center flex flex-col items-center justify-center gap-2 shadow-2xs">
        <div className="w-9 h-9 rounded-xl bg-neutral-100 flex items-center justify-center text-neutral-400">
          <Phone className="w-4 h-4" />
        </div>
        <div>
          <p className="text-xs font-semibold text-neutral-900">No Call Records Found</p>
          <p className="text-xs text-neutral-400 max-w-sm mt-0.5">
            {searchQuery
              ? `No calls match "${searchQuery}". Clear your search query.`
              : 'Inbound calls connecting to your clinic will automatically appear here.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.dateLabel} className="space-y-1.5">
          <div className="flex items-center gap-2 px-1">
            <span className="text-xs font-semibold tracking-tight text-neutral-800">
              {group.dateLabel}
            </span>
            <span className="text-[10px] font-mono font-medium text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded">
              {group.items.length} {group.items.length === 1 ? 'call' : 'calls'}
            </span>
          </div>

          <div className="rounded-xl border border-neutral-200/90 bg-white overflow-hidden shadow-2xs divide-y divide-neutral-100">
            {group.items.map((call) => (
              <CallRecordCard
                key={call.id}
                call={call}
                isExpanded={expandedId === call.id}
                isPlaying={activePlayingId === call.id}
                copiedId={copiedId}
                onToggleExpand={() => onToggleExpand(call.id)}
                onTogglePlay={onTogglePlay}
                onCopy={onCopy}
                formatTime={formatTime}
                formatDate={formatDate}
                formatDuration={formatDuration}
                isMissedCall={isMissedCall}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
