'use client';

import React from 'react';
import { Check, Play, Square, Loader2 } from 'lucide-react';
import { VOICE_PERSONAS, VoicePersona, normalizeVoicePersona } from '../../constants';

interface PersonaGridProps {
  voicePersona: string;
  playingSampleId: string | null;
  loadingSampleId: string | null;
  onSelectVoice: (persona: VoicePersona) => void;
  onPlaySample: (event: React.MouseEvent, persona: VoicePersona) => void;
  onStopAudio: () => void;
}

export function PersonaGrid({ voicePersona, playingSampleId, loadingSampleId, onSelectVoice, onPlaySample, onStopAudio }: PersonaGridProps) {
  const selectedId = normalizeVoicePersona(voicePersona);
  return (
    <section className="order-2 overflow-hidden rounded-2xl border border-neutral-200/80 bg-white xl:order-none">
      <header className="border-b border-neutral-100 px-5 py-4"><h3 id="receptionist-voice-label" className="text-sm font-semibold tracking-tight text-neutral-900">Receptionist voice</h3><p className="mt-1 text-xs leading-relaxed text-neutral-500">Listen to a sample, then choose a voice.</p></header>
      <div role="radiogroup" aria-labelledby="receptionist-voice-label" className="divide-y divide-neutral-100">
        {VOICE_PERSONAS.map((voice) => {
          const selected = selectedId === voice.id;
          const playing = playingSampleId === voice.id;
          const loading = loadingSampleId === voice.id;
          return (
            <div key={voice.id} className={`flex items-center gap-2 px-4 transition ${selected ? 'bg-[#E3EBE0]/45' : 'hover:bg-neutral-50/80'}`}>
              <label className="flex min-h-[72px] min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-lg py-3 focus-within:outline-none focus-within:ring-2 focus-within:ring-[#1E6B56]">
                <input type="radio" name="receptionist-voice" value={voice.id} checked={selected} onChange={() => onSelectVoice(voice)} className="sr-only" />
                <span aria-hidden="true" className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-medium ${selected ? 'border-[#1E6B56] bg-[#1E6B56] text-white' : 'border-neutral-200 bg-neutral-50 text-neutral-500'}`}>{selected ? <Check className="h-3.5 w-3.5" /> : voice.label.slice(0, 1)}</span>
                <span className="min-w-0"><span className={`block text-sm ${selected ? 'font-semibold text-[#143530]' : 'font-medium text-neutral-800'}`}>{voice.label}</span><span role={loading ? 'status' : undefined} className="mt-0.5 block truncate text-[11px] text-neutral-500">{loading ? 'Preparing sample…' : `${voice.accent}${voice.gender ? ` · ${voice.gender === 'feminine' ? 'Female' : 'Male'}` : ''}`}</span></span>
              </label>
              <button type="button" onClick={(event) => (playing || loading) ? onStopAudio() : onPlaySample(event, voice)} aria-busy={loading} aria-label={loading ? `Cancel ${voice.label} sample loading` : playing ? `Stop ${voice.label} sample` : `Listen to ${voice.label}`} title={loading ? 'Preparing sample — click to cancel' : playing ? 'Stop sample' : 'Listen to sample'} className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E6B56] focus-visible:ring-offset-2 ${playing || loading ? 'border-[#1E6B56] bg-[#1E6B56] text-white' : 'border-neutral-200 bg-white text-neutral-500 hover:border-[#BFDDCD] hover:text-[#1E6B56]'}`}>{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : playing ? <Square className="h-3 w-3 fill-current" /> : <Play className="ml-0.5 h-3 w-3 fill-current" />}</button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
