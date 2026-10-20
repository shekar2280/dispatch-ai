'use client';

import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { Loader2, AlertTriangle, RotateCcw, CheckCheck, PhoneMissed } from 'lucide-react';
import { useClinicStore } from '../store';
import { createClient } from '@/lib/supabase/client';
import { CallsHeader } from './_components/CallsHeader';
import { CallsFilterBar } from './_components/CallsFilterBar';
import { CallsList } from './_components/CallsList';
import { useClinicCallsQuery, clinicQueryKeys } from '../_hooks/useClinicQueries';
import { useQueryClient } from '@tanstack/react-query';
import { ClinicCallSessionItem } from '../types';
import { useCallEvents } from './_hooks/useCallEvents';
import { httpClient } from '@/lib/api/httpClient';

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
  audio_recording_url?: string | null;
}

type TabType = 'all' | 'missed' | 'ai' | 'emergency';

export default function ClinicCallsPage() {
  const orgId = useClinicStore((s) => s.orgId);
  useCallEvents(orgId);
  const missedCallsCount = useClinicStore((s) => s.missedCallsCount);
  const markCallsAsViewed = useClinicStore((s) => s.markCallsAsViewed);
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<TabType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedSearch(searchQuery); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [searchQuery]);
  const {
    data: callPage,
    isLoading,
    isRefetching,
    refetch,
    error,
  } = useClinicCallsQuery(orgId, { page, search: debouncedSearch, targetDate: selectedDate, category: activeTab });
  const calls = callPage?.logs || [];


  const [activePlayingId, setActivePlayingId] = useState<string | null>(null);
  const [audioInstance, setAudioInstance] = useState<HTMLAudioElement | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState('');

  const fetchCalls = useCallback(() => {
    refetch();
  }, [refetch]);

  useEffect(() => {
    if (!orgId) return;

    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const supabase = createClient();
    const channel = supabase
      .channel(`voice-calls-${orgId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'call_logs', filter: `org_id=eq.${orgId}` },
        () => {
          if (refreshTimer) return;
          refreshTimer = setTimeout(() => {
            refreshTimer = undefined;
            void queryClient.invalidateQueries({ queryKey: clinicQueryKeys.calls(orgId) }, { cancelRefetch: false });
          }, 250);
        }
      )
      .subscribe();

    return () => {
      if (refreshTimer) clearTimeout(refreshTimer);
      supabase.removeChannel(channel);
    };
  }, [orgId, queryClient]);

  useEffect(() => {
    return () => {
      if (audioInstance) audioInstance.pause();
    };
  }, [audioInstance]);

  const isMissedCall = (call: CallSession) =>
    Boolean(
      call.is_missed ||
      call.triage_status === 'MISSED' ||
      call.call_outcome === 'missed' ||
      call.call_outcome === 'caller_abandoned' ||
      call.call_outcome === 'caller_silent' ||
      call.call_outcome === 'no_answer' ||
      call.call_outcome === 'ringing' ||
      call.handled_by?.toLowerCase().includes('missed') ||
      call.handled_by?.toLowerCase().includes('unattended') ||
      ((call.duration_seconds || 0) === 0 && !call.audio_recording_url && !call.summary?.includes('Appointment booked'))
    );

  const togglePlay = async (e: React.MouseEvent, id: string, audioUrl?: string | null) => {
    e.stopPropagation();
    if (audioInstance) {
      audioInstance.pause();
      setAudioInstance(null);
    }
    if (activePlayingId === id) {
      setActivePlayingId(null);
      return;
    }
    if (audioUrl) {
      setPlaybackError('');
      try {
        const recording = await httpClient.get<{ url: string }>(`/api/v1/calls/call-sessions/${id}/recording`, { orgId });
        const newAudio = new Audio(recording.url);
        await newAudio.play();
        newAudio.onended = () => setActivePlayingId(null);
        newAudio.onerror = () => { setPlaybackError('Recording playback failed. Please try again.'); setActivePlayingId(null); };
        setAudioInstance(newAudio);
        setActivePlayingId(id);
      } catch {
        setPlaybackError('Recording is unavailable. Please try again.');
        setActivePlayingId(null);
      }
    }
  };

  const copyToClipboard = async (e: React.MouseEvent, id: string, text: string) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1800);
    } catch { }
  };

  const formatDuration = (seconds: number) => {
    if (!seconds || seconds <= 0) return '0s';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  const formatTime = (isoString: string) => {
    if (!isoString) return '—';
    try {
      return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoString;
    }
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return '—';
    try {
      return new Date(isoString).toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  const getDayHeading = (isoString: string) => {
    if (!isoString) return 'Earlier Records';
    try {
      const callDate = new Date(isoString);
      if (isNaN(callDate.getTime())) return 'Earlier Records';
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const target = new Date(callDate.getFullYear(), callDate.getMonth(), callDate.getDate());
      const diffDays = Math.round((today.getTime() - target.getTime()) / (1000 * 60 * 60 * 24));
      if (diffDays === 0) return 'Today';
      if (diffDays === 1) return 'Yesterday';
      return callDate.toLocaleDateString(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: callDate.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
      });
    } catch {
      return 'Earlier Records';
    }
  };

  const filteredCalls = calls;

  const groupedCalls = useMemo(() => {
    const groups: { dateLabel: string; items: CallSession[] }[] = [];
    filteredCalls.forEach((call) => {
      const label = getDayHeading(call.start_time);
      const lastGroup = groups[groups.length - 1];
      if (lastGroup && lastGroup.dateLabel === label) {
        lastGroup.items.push(call);
      } else {
        groups.push({ dateLabel: label, items: [call] });
      }
    });
    return groups;
  }, [filteredCalls]);



  return (
    <div className="w-full space-y-4 font-sans text-neutral-900 pb-20">
      <CallsHeader
        isLoading={isLoading}
        isRevalidating={isRefetching}
        onRefresh={() => fetchCalls()}
        selectedDate={selectedDate}
        onDateChange={(value) => { setSelectedDate(value); setPage(1); }}
      />

      {missedCallsCount > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-100 bg-white px-4 py-3">
          <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-rose-50 text-rose-600"><PhoneMissed className="h-4 w-4" /></span>
            <div><p className="text-sm font-semibold text-neutral-900">{missedCallsCount} new missed {missedCallsCount === 1 ? 'call' : 'calls'}</p><p className="mt-0.5 text-xs text-neutral-500">Mark as seen to clear the sidebar badge. Calls stay in your history.</p></div>
          </div>
          <button type="button" onClick={markCallsAsViewed} className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3 text-xs font-medium text-neutral-700 hover:bg-neutral-50 focus-visible:ring-2 focus-visible:ring-emerald-700"><CheckCheck className="h-4 w-4" />Mark all as seen</button>
        </div>
      )}

      {playbackError && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">{playbackError}</p>}
      {error && (
        <div className="p-3.5 rounded-2xl bg-rose-50/90 border border-rose-200 text-rose-800 flex items-center justify-between gap-3 shadow-2xs">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <p className="text-xs font-medium leading-normal">
              {(error as any)?.message || 'Unable to retrieve call records.'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => fetchCalls()}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-xl bg-rose-100 text-rose-800 hover:bg-rose-200 active:scale-95 transition-all cursor-pointer shrink-0"
          >
            <RotateCcw className="w-3 h-3" />
            Retry
          </button>
        </div>
      )}

      <CallsFilterBar
        activeTab={activeTab}
        onTabChange={(value) => { setActiveTab(value); setPage(1); }}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        counts={callPage?.counts || { all: 0, ai: 0, emergency: 0, missed: 0 }}
      />

      {isLoading && calls.length === 0 ? (
        <div className="space-y-5 animate-pulse select-none">
          <div className="space-y-2.5">
            <div className="flex items-center gap-2.5 px-1 pt-1">
              <div className="h-3.5 w-20 bg-neutral-200 rounded" />
              <div className="h-3.5 w-14 bg-neutral-100 rounded-full" />
              <div className="h-px bg-neutral-200/70 flex-1" />
            </div>

            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="rounded-2xl border border-neutral-200/90 p-3.5 sm:p-4 bg-white shadow-2xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-xl bg-neutral-100 border border-neutral-200 shrink-0" />
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="h-4 w-32 bg-neutral-200 rounded font-mono" />
                        <div className="h-3.5 w-28 bg-neutral-100 rounded" />
                      </div>
                      <div className="h-3 w-48 bg-neutral-100 rounded" />
                    </div>
                  </div>
                  <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
                    <div className="w-20 h-6 bg-neutral-100 border border-neutral-200/70 rounded-full" />
                    <div className="w-20 h-6 bg-neutral-100 border border-neutral-200/70 rounded-full" />
                    <div className="w-20 h-8 bg-neutral-100 border border-neutral-200 rounded-xl" />
                    <div className="w-24 h-8 bg-neutral-100 border border-neutral-200 rounded-xl" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <CallsList
          groups={groupedCalls}
          searchQuery={searchQuery}
          expandedId={expandedId}
          activePlayingId={activePlayingId}
          copiedId={copiedId}
          onToggleExpand={(id) => setExpandedId(expandedId === id ? null : id)}
          onTogglePlay={togglePlay}
          onCopy={copyToClipboard}
          formatTime={formatTime}
          formatDate={formatDate}
          formatDuration={formatDuration}
          isMissedCall={isMissedCall}
        />
      )}
      <div className="flex items-center justify-between gap-3 text-xs text-neutral-500">
        <span>{callPage?.total || 0} matching calls · Page {page}</span>
        <div className="flex gap-3">
          <button disabled={page === 1 || isLoading} onClick={() => setPage(page - 1)} className="rounded-lg border border-neutral-200 bg-white px-3 py-2 disabled:opacity-40">Previous</button>
          <button disabled={!callPage?.has_more || isLoading} onClick={() => setPage(page + 1)} className="rounded-lg border border-neutral-200 bg-white px-3 py-2 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}
