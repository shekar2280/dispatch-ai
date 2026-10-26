'use client';

import React from 'react';
import { Square, Loader2, Play, AudioLines } from 'lucide-react';
import { VOICE_PERSONAS, VoicePersona, normalizeVoicePersona } from '../../constants';
import { useClinicSettings } from '../../_context/ClinicSettingsContext';
import { GreetingEditor } from './GreetingEditor';
import { PersonaGrid } from './PersonaGrid';

export function AiVoiceSection() {
  const { clinicName, greetingPrompt, setGreetingPrompt, voicePersona, isLoadingAudio, audioPreviewError, isPlayingAudio, playingSampleId, loadingSampleId, playGreetingPreview, playPersonaSample, stopAudioPreview, handleSelectVoice } = useClinicSettings();
  const selectedVoice = VOICE_PERSONAS.find((voice) => voice.id === normalizeVoicePersona(voicePersona)) || VOICE_PERSONAS[0];
  const defaultGreeting = `Hello! Welcome to ${clinicName.trim() || 'our clinic'}. How can I help you today?`;
  const previewGreeting = () => {
    if (isPlayingAudio) stopAudioPreview();
    else playGreetingPreview(greetingPrompt.trim() || defaultGreeting, voicePersona);
  };
  const selectVoice = (voice: VoicePersona) => { stopAudioPreview(); handleSelectVoice(voice); };
  const editGreeting = (text: string) => {
    if (isPlayingAudio || isLoadingAudio || playingSampleId || loadingSampleId) stopAudioPreview();
    setGreetingPrompt(text);
  };

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
      <PersonaGrid voicePersona={voicePersona} playingSampleId={playingSampleId} loadingSampleId={loadingSampleId} onSelectVoice={selectVoice} onPlaySample={playPersonaSample} onStopAudio={stopAudioPreview} />
      <section className="order-1 min-w-0 overflow-hidden rounded-2xl border border-neutral-200/80 bg-white xl:order-none">
        <header className="border-b border-neutral-100 px-5 py-4"><h3 className="text-sm font-semibold tracking-tight text-neutral-900">Opening greeting</h3><p className="mt-1 text-xs leading-relaxed text-neutral-500">The first words callers hear. Keep it friendly and brief.</p></header>
        <div className="p-5"><GreetingEditor greetingPrompt={greetingPrompt} setGreetingPrompt={editGreeting} clinicName={clinicName} /></div>
        <div className="border-t border-neutral-100 bg-[#F6F8F4] p-5">
          <div className="flex items-center gap-3"><span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#BFDDCD]/50 bg-white text-[#1E6B56] ${isPlayingAudio ? 'motion-safe:animate-pulse' : ''}`}><AudioLines className="h-5 w-5" /></span><div className="min-w-0"><p className="text-sm font-medium text-neutral-900">{selectedVoice.label}<span className="ml-2 text-[11px] font-normal text-neutral-500">{selectedVoice.tone}</span></p><p className="mt-0.5 text-xs text-neutral-500">{isPlayingAudio ? 'Playing your opening greeting…' : isLoadingAudio ? 'Preparing your greeting…' : 'Hear your greeting in the selected voice.'}</p></div></div>
          <button type="button" disabled={isLoadingAudio} onClick={previewGreeting} className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#0D2622] px-4 text-sm font-medium text-white transition hover:bg-[#1E6B56] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E6B56] focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60">{isLoadingAudio ? <Loader2 className="h-4 w-4 animate-spin" /> : isPlayingAudio ? <Square className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current text-[#BFDDCD]" />}{isLoadingAudio ? 'Preparing audio…' : isPlayingAudio ? 'Stop preview' : 'Preview greeting'}</button>
          {audioPreviewError && <p role="alert" className="mt-3 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2 text-xs text-rose-700">{audioPreviewError}</p>}
        </div>
      </section>
    </div>
  );
}
