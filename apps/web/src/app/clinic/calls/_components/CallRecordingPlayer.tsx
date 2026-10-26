'use client';

import { useEffect, useRef, useState } from 'react';
import type WaveSurfer from 'wavesurfer.js';
import { httpClient } from '@/lib/api/httpClient';
import { useClinicStore } from '../../store';

export interface ConversationTurn {
  role: string;
  text: string;
  offset_seconds?: number;
}

export function CallRecordingPlayer({ callId, recordingStatus, turns = [], transcript }: {
  callId: string;
  recordingStatus?: string | null;
  turns?: ConversationTurn[];
  transcript?: string | null;
}) {
  const orgId = useClinicStore((state) => state.orgId);
  const container = useRef<HTMLDivElement>(null);
  const player = useRef<WaveSurfer | null>(null);
  const mounted = useRef(true);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  const [position, setPosition] = useState(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      player.current?.destroy();
      player.current = null;
    };
  }, [callId]);

  async function togglePlayback() {
    if (loading) return;
    if (player.current) {
      try { await player.current.playPause(); }
      catch { setError('Playback failed. Please try again.'); }
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [{ default: WaveSurfer }, recording] = await Promise.all([
        import('wavesurfer.js'),
        httpClient.get<{ url: string }>(`/api/v1/calls/call-sessions/${callId}/recording`, { orgId }),
      ]);
      if (!mounted.current || !container.current) return;
      const instance = WaveSurfer.create({ container: container.current, height: 52,
        waveColor: '#a3a3a3', progressColor: '#2563eb', cursorColor: '#171717', barWidth: 2, barGap: 2 });
      player.current = instance;
      instance.on('play', () => setPlaying(true));
      instance.on('pause', () => setPlaying(false));
      instance.on('finish', () => setPlaying(false));
      instance.on('timeupdate', setPosition);
      instance.on('error', () => {
        if (mounted.current) { setError('Recording could not be loaded. Please try again.'); setPlaying(false); }
        instance.destroy();
        if (player.current === instance) player.current = null;
      });
      await instance.load(recording.url);
      if (mounted.current) await instance.play();
    } catch {
      if (mounted.current) setError('Recording is unavailable. Please try again.');
      player.current?.destroy();
      player.current = null;
    } finally {
      if (mounted.current) setLoading(false);
    }
  }

  const activeTurn = turns.findLastIndex((turn) => typeof turn.offset_seconds === 'number' && turn.offset_seconds <= position);

  return (
    <section className="rounded-xl border border-neutral-200 bg-white p-3 space-y-3" onClick={(event) => event.stopPropagation()}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xs font-semibold text-neutral-800">Recording &amp; transcript</h3>
        {recordingStatus === 'ready' || recordingStatus === 'partial' ? (
          <button type="button" onClick={() => void togglePlayback()} disabled={loading}
            className="rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
            {loading ? 'Loading…' : playing ? 'Pause' : recordingStatus === 'partial' ? 'Play partial recording' : 'Play recording'}
          </button>
        ) : <span className="text-xs text-neutral-500">{recordingStatus === 'processing' ? 'Recording processing' : recordingStatus === 'failed' ? 'Recording unavailable' : turns.length > 0 || transcript ? 'Audio purged (retention policy)' : 'No recording'}</span>}
      </div>
      <div ref={container} aria-label="Call recording waveform" />
      {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
      {turns.length ? (
        <ol className="max-h-72 space-y-2 overflow-y-auto">
          {turns.map((turn, index) => (
            <li key={index} className={`rounded-lg p-2 text-xs ${index === activeTurn && playing ? 'bg-blue-50 text-blue-950' : 'bg-neutral-50 text-neutral-700'}`}>
              <button type="button" disabled={!player.current || typeof turn.offset_seconds !== 'number'}
                onClick={() => player.current?.setTime(turn.offset_seconds || 0)} className="text-left leading-relaxed disabled:cursor-default">
                <strong className="mr-2">{turn.role === 'user' ? 'Caller' : 'Receptionist'}</strong>{turn.text}
              </button>
            </li>
          ))}
        </ol>
      ) : <p className="text-xs whitespace-pre-line text-neutral-600">{transcript || 'No transcript recorded.'}</p>}
    </section>
  );
}
