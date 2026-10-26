"use client";

import { useState, useRef, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { VoicePersona } from "../constants";
import { API_BASE_URL } from "@/lib/constants";

interface UseVoiceAudioPreviewOptions {
  clinicName: string;
  greetingPrompt: string;
  voicePersona: string;
}

export function useVoiceAudioPreview({
  clinicName,
  greetingPrompt,
  voicePersona,
}: UseVoiceAudioPreviewOptions) {
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const sampleAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioBlobCacheRef = useRef<Map<string, string>>(new Map());
  const pendingAudioRef = useRef<Map<string, Promise<string>>>(new Map());
  const requestIdRef = useRef(0);

  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [isLoadingAudio, setIsLoadingAudio] = useState(false);
  const [playingSampleId, setPlayingSampleId] = useState<string | null>(null);
  const [loadingSampleId, setLoadingSampleId] = useState<string | null>(null);
  const [audioPreviewError, setAudioPreviewError] = useState<string | null>(null);

  const stopAudioPreview = () => {
    requestIdRef.current += 1;
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }
    if (sampleAudioRef.current) {
      sampleAudioRef.current.pause();
      sampleAudioRef.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setIsPlayingAudio(false);
    setIsLoadingAudio(false);
    setPlayingSampleId(null);
    setLoadingSampleId(null);
    setAudioPreviewError(null);
  };

  useEffect(() => () => {
    requestIdRef.current += 1;
    previewAudioRef.current?.pause();
    sampleAudioRef.current?.pause();
    audioBlobCacheRef.current.forEach((url) => URL.revokeObjectURL(url));
    audioBlobCacheRef.current.clear();
  }, []);

  const getPreviewUrl = async (text: string, voiceId: string) => {
    const cacheKey = `${voiceId}:${text.trim()}`;
    const cached = audioBlobCacheRef.current.get(cacheKey);
    if (cached) {
      // Refresh insertion order so frequently replayed previews stay cached.
      audioBlobCacheRef.current.delete(cacheKey);
      audioBlobCacheRef.current.set(cacheKey, cached);
      return cached;
    }
    const pending = pendingAudioRef.current.get(cacheKey);
    if (pending) return pending;

    const request = (async () => {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }
      const res = await fetch(`${API_BASE_URL}/api/v1/org/voice-preview`, {
        method: "POST",
        headers,
        body: JSON.stringify({ text, voice_id: voiceId }),
      });
      if (!res.ok) throw new Error("Voice preview could not be generated");
      const url = URL.createObjectURL(await res.blob());
      audioBlobCacheRef.current.set(cacheKey, url);
      while (audioBlobCacheRef.current.size > 40) {
        const oldestKey = audioBlobCacheRef.current.keys().next().value;
        if (!oldestKey) break;
        const oldestUrl = audioBlobCacheRef.current.get(oldestKey);
        audioBlobCacheRef.current.delete(oldestKey);
        if (oldestUrl) URL.revokeObjectURL(oldestUrl);
      }
      return url;
    })();
    pendingAudioRef.current.set(cacheKey, request);
    try { return await request; }
    finally { pendingAudioRef.current.delete(cacheKey); }
  };

  const playGreetingPreview = async (
    customText?: string,
    customVoiceId?: string,
  ) => {
    const rawText = customText !== undefined ? customText : greetingPrompt;
    const resolvedClinic = clinicName.trim() || "our clinic";
    const textToSpeak = rawText
      .replace(/\{\{clinic_name\}\}/gi, resolvedClinic)
      .replace(/\{clinic_name\}/gi, resolvedClinic);
    const voiceToUse =
      customVoiceId !== undefined ? customVoiceId : voicePersona;
    if (!textToSpeak.trim()) return;

    if (sampleAudioRef.current) {
      sampleAudioRef.current.pause();
      setPlayingSampleId(null);
      sampleAudioRef.current = null;
    }
    setPlayingSampleId(null);
    setLoadingSampleId(null);
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }

    const requestId = ++requestIdRef.current;
    setAudioPreviewError(null);
    setIsLoadingAudio(true);
    try {
      const audioUrl = await getPreviewUrl(textToSpeak, voiceToUse);
      if (requestId === requestIdRef.current) {
        const audio = new Audio(audioUrl);
        previewAudioRef.current = audio;
        setIsLoadingAudio(false);
        setIsPlayingAudio(true);
        audio.onended = () => {
          setIsPlayingAudio(false);
        };
        audio.onerror = () => {
          setIsPlayingAudio(false);
        };
        await audio.play();
        return;
      }
    } catch {
      if (requestId === requestIdRef.current) {
        setIsPlayingAudio(false);
        setAudioPreviewError('Audio could not be prepared. Please try again.');
      }
    } finally {
      if (requestId === requestIdRef.current) setIsLoadingAudio(false);
    }

  };

  const playPersonaSample = async (
    e: React.MouseEvent,
    persona: VoicePersona,
  ) => {
    e.stopPropagation();
    const cancelCurrentSample = playingSampleId === persona.id || loadingSampleId === persona.id;
    stopAudioPreview();
    if (cancelCurrentSample) return;

    const requestId = ++requestIdRef.current;
    setLoadingSampleId(persona.id);
    try {
      const phrase = persona.defaultPhrase || greetingPrompt;
      const resolvedPhrase = phrase.replace(/\{\{?clinic_name\}?\}/gi, clinicName.trim() || "our clinic");
      const audioUrl = await getPreviewUrl(resolvedPhrase, persona.id);
      if (requestId !== requestIdRef.current) return;
      const audio = new Audio(audioUrl);
      sampleAudioRef.current = audio;
      audio.onplaying = () => {
        if (requestId !== requestIdRef.current) { audio.pause(); return; }
        setLoadingSampleId(null);
        setPlayingSampleId(persona.id);
      };
      audio.onended = () => {
        if (requestId !== requestIdRef.current) return;
        setPlayingSampleId(null);
        setLoadingSampleId(null);
        sampleAudioRef.current = null;
      };
      audio.onerror = () => {
        if (requestId !== requestIdRef.current) return;
        setPlayingSampleId(null);
        setLoadingSampleId(null);
        sampleAudioRef.current = null;
        setAudioPreviewError('Audio could not be played. Please try again.');
      };
      await audio.play();
    } catch {
      if (requestId !== requestIdRef.current) return;
      setLoadingSampleId(null);
      setPlayingSampleId(null);
      sampleAudioRef.current = null;
      setAudioPreviewError('Audio could not be prepared. Please try again.');
    }
  };

  return {
    isPlayingAudio,
    isLoadingAudio,
    audioPreviewError,
    playingSampleId,
    loadingSampleId,
    playGreetingPreview,
    playPersonaSample,
    stopAudioPreview,
  };
}
