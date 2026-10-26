'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  PhoneCall,
  PhoneOff,
  Mic,
  MicOff,
  Volume2,
  X,
  RefreshCw,
  AlertCircle,
  Building2,
  Sparkles,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  UserRound,
  BadgeCheck,
  Clock,
  ArrowUpRight,
  Headphones,
  Check,
  Search,
  Plus,
} from 'lucide-react';
import { Room, RoomEvent, TranscriptionSegment, Participant, setLogLevel, createLocalAudioTrack, LocalAudioTrack } from 'livekit-client';
import { VoiceSimulatorModalProps, ChatTurn } from '@/types';
import { API_BASE_URL } from '@/lib/constants';
import { useOrgId } from '@/components/providers/OrgContext';
import { useClinicPatientsQuery } from '../_hooks/useClinicQueries';
import { createClient } from '@/lib/supabase/client';
import { useQueryClient } from '@tanstack/react-query';
import { clinicQueryKeys } from '../_hooks/useClinicQueries';

if (typeof window !== 'undefined') {
  setLogLevel('warn');
}

function sanitizeErrorMessage(rawError?: string | null): string {
  if (!rawError) return 'The clinic reception line is temporarily unavailable. Please try your call again in a moment.';
  const lower = rawError.toLowerCase();
  if (lower.includes('voice minutes') || lower.includes('30 minute')) return 'This clinic has used its available voice minutes. Ask the administrator for extra minutes.';
  if (lower.includes('already has a call')) return 'This clinic already has a call connecting or in progress.';
  if (lower.includes('permission') || lower.includes('notallowed')) return 'Allow microphone access to test a call.';
  if (
    lower.includes('429') ||
    lower.includes('quota') ||
    lower.includes('rate') ||
    lower.includes('busy') ||
    lower.includes('capacity') ||
    lower.includes('limit') ||
    lower.includes('concurrent') ||
    lower.includes('line_busy')
  ) {
    return 'All automated reception lines are currently handling maximum caller volume. Please wait a moment and try calling again.';
  }
  if (
    lower.includes('timeout') ||
    lower.includes('took too long') ||
    lower.includes('failed to fetch') ||
    lower.includes('network') ||
    lower.includes('connection')
  ) {
    return 'Unable to establish a stable connection with the clinic phone exchange. Please check your network and try again.';
  }
  return 'The clinic phone line is temporarily busy due to high demand. Please try calling again in a moment.';
}

const PENDING_SIMULATOR_FAILURES_KEY = 'dispatch_pending_simulator_missed_calls';

type PendingSimulatorFailure = {
  org_id: string;
  room_name: string;
  caller_phone: string;
  caller_name: string;
  call_outcome: 'caller_abandoned' | 'service_unavailable' | 'line_busy';
  queued_at?: number;
};

async function syncSimulatorFailure(failure: PendingSimulatorFailure) {
  try {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    headers['X-Org-Id'] = failure.org_id;
    if (session?.access_token) {
      headers['Authorization'] = `Bearer ${session.access_token}`;
    }

    const response = await fetch(
      `${API_BASE_URL}/api/v1/voice/calls/${encodeURIComponent(failure.room_name)}/simulator-end`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(failure),
        keepalive: true,
      }
    );
    return response.ok || response.status === 404;
  } catch {
    return false;
  }
}

async function queueSimulatorFailure(failure: PendingSimulatorFailure) {
  try {
    const pending: PendingSimulatorFailure[] = JSON.parse(
      localStorage.getItem(PENDING_SIMULATOR_FAILURES_KEY) || '[]'
    );
    if (!pending.some((item) => item.room_name === failure.room_name)) {
      pending.push({ ...failure, queued_at: Date.now() });
      localStorage.setItem(PENDING_SIMULATOR_FAILURES_KEY, JSON.stringify(pending));
    }
  } catch { }

  try {
    if (await syncSimulatorFailure(failure)) {
      const pending: PendingSimulatorFailure[] = JSON.parse(
        localStorage.getItem(PENDING_SIMULATOR_FAILURES_KEY) || '[]'
      );
      localStorage.setItem(
        PENDING_SIMULATOR_FAILURES_KEY,
        JSON.stringify(pending.filter((item) => item.room_name !== failure.room_name))
      );
    }
  } catch { }
}

async function flushQueuedSimulatorFailures() {
  try {
    const pending: PendingSimulatorFailure[] = JSON.parse(
      localStorage.getItem(PENDING_SIMULATOR_FAILURES_KEY) || '[]'
    );
    const remaining: PendingSimulatorFailure[] = [];
    for (const failure of pending.slice(-25)) {
      if (!failure.queued_at || Date.now() - failure.queued_at > 86400000) continue;
      try {
        if (!(await syncSimulatorFailure(failure))) remaining.push(failure);
      } catch {
        remaining.push(failure);
      }
    }
    localStorage.setItem(PENDING_SIMULATOR_FAILURES_KEY, JSON.stringify(remaining));
  } catch { }
}

function normalizeCallerNumber(value: string) {
  const digits = value.replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) return digits.slice(2);
  if (digits.length === 11 && digits.startsWith('0')) return digits.slice(1);
  return digits;
}

export function VoiceSimulatorModal({ isOpen, onClose, orgId: propOrgId }: VoiceSimulatorModalProps) {
  const activeOrgId = useOrgId();
  const orgId = propOrgId || activeOrgId;
  const queryClient = useQueryClient();
  const refreshCallResults = useCallback(() => {
    for (const key of [clinicQueryKeys.appointments(orgId), clinicQueryKeys.patients(orgId),
    clinicQueryKeys.dashboard(orgId), clinicQueryKeys.calls(orgId)]) {
      void queryClient.invalidateQueries({ queryKey: key, refetchType: 'active' }, { cancelRefetch: false });
    }
  }, [orgId, queryClient]);
  const { data: clinicPatients = [], refetch: refreshClinicPatients } = useClinicPatientsQuery(orgId, isOpen);
  const [callerPhone, setCallerPhone] = useState('+91 98765 43210');
  const [callerName, setCallerName] = useState('');
  const [selectedCallerId, setSelectedCallerId] = useState<string | null>(null);
  const [isCallerPickerOpen, setIsCallerPickerOpen] = useState(false);
  const [callerSearch, setCallerSearch] = useState('');
  const [activeCallerIndex, setActiveCallerIndex] = useState(0);
  const [callerPickerPlacement, setCallerPickerPlacement] = useState<'above' | 'below'>('below');
  const [callerOptionsHeight, setCallerOptionsHeight] = useState(168);
  const callerPickerRef = useRef<HTMLDivElement | null>(null);
  const callerPickerButtonRef = useRef<HTMLButtonElement | null>(null);
  const callerSearchRef = useRef<HTMLInputElement | null>(null);
  const [clinicDetails, setClinicDetails] = useState<{
    name: string;
    leadDoctor?: string;
    specialty?: string;
    phone?: string;
  } | null>(null);
  const [voiceAllowance, setVoiceAllowance] = useState<{
    remaining_seconds: number;
    used_seconds: number;
    limit_seconds: number;
    max_call_seconds: number;
  } | null>(null);
  const [allowanceStatus, setAllowanceStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [sessionLimit, setSessionLimit] = useState(120);
  const [limitReached, setLimitReached] = useState(false);
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const callStartedAtRef = useRef<number | null>(null);

  const [callState, setCallState] = useState<'idle' | 'dialing' | 'ringing' | 'connected' | 'ended'>('idle');
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [showTranscript, setShowTranscript] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [chatLog, setChatLog] = useState<ChatTurn[]>([]);
  const [callSeconds, setCallSeconds] = useState(0);

  const roomRef = useRef<Room | null>(null);
  const microphoneRef = useRef<LocalAudioTrack | null>(null);
  const callAttemptRef = useRef(0);
  const connectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callerIdentityEditedRef = useRef(false);
  const roomNameRef = useRef<string | null>(null);
  const simulatorEndReasonRef = useRef<PendingSimulatorFailure['call_outcome']>('caller_abandoned');
  const ringAudioCtxRef = useRef<AudioContext | null>(null);
  const ringOscillatorRef = useRef<{ stop: () => void } | null>(null);
  const segmentMapRef = useRef<Map<string, { sender: 'ai' | 'user'; text: string; final: boolean; timestamp: string }>>(new Map());
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const phoneMatches = clinicPatients.filter(
    (patient) => normalizeCallerNumber(patient.phone) === normalizeCallerNumber(callerPhone)
  );
  const matchedPatient = phoneMatches.find((patient) => patient.id === selectedCallerId)
    ?? (phoneMatches.length === 1 ? phoneMatches[0] : undefined);
  const needsCallerSelection = phoneMatches.length > 1 && !matchedPatient;
  const savedCallerProfiles = Array.from(
    new Map(
      clinicPatients.map((patient) => [patient.id, patient] as const)
    ).values()
  );
  const filteredCallerProfiles = savedCallerProfiles.filter((patient) => {
    const query = callerSearch.trim().toLowerCase();
    return patient.name.toLowerCase().includes(query)
      || (normalizeCallerNumber(query).length > 0 && normalizeCallerNumber(patient.phone).includes(normalizeCallerNumber(query)));
  });
  const simulatorCallerName = callerName.trim() || matchedPatient?.name || 'Incoming Caller';
  const isCalling = callState === 'dialing' || callState === 'ringing' || callState === 'connected';
  const configuredCallLimit = Math.min(120, Math.max(1, voiceAllowance?.max_call_seconds ?? 120));
  const maxCallSeconds = callState === 'idle' ? configuredCallLimit : sessionLimit;
  const remainingCallSeconds = Math.max(0, maxCallSeconds - callSeconds);
  const isNearCallLimit = callState === 'connected' && remainingCallSeconds <= 30;
  const quotaExhausted = voiceAllowance !== null && voiceAllowance.remaining_seconds <= 0;
  const canStartCall = Boolean(orgId) && normalizeCallerNumber(callerPhone).length >= 10
    && allowanceStatus === 'ready' && !quotaExhausted && !isCalling && !needsCallerSelection;

  function chooseCaller(patient?: (typeof clinicPatients)[number]) {
    setSelectedCallerId(patient?.id ?? null);
    setCallerPhone(patient?.phone ?? '');
    setCallerName(patient?.name ?? '');
    setIsCallerPickerOpen(false);
    setCallerSearch('');
    callerPickerButtonRef.current?.focus();
  }

  useEffect(() => {
    if (!isCallerPickerOpen) return;
    callerSearchRef.current?.focus();
    const positionPicker = () => {
      const trigger = callerPickerButtonRef.current?.getBoundingClientRect();
      const dialog = dialogRef.current?.getBoundingClientRect();
      if (!trigger || !dialog) return;
      const below = Math.min(dialog.bottom, window.innerHeight) - trigger.bottom;
      const above = trigger.top - Math.max(dialog.top, 0);
      const openAbove = below < 220 && above > below;
      setCallerPickerPlacement(openAbove ? 'above' : 'below');
      setCallerOptionsHeight(Math.max(64, Math.min(210, window.innerHeight * 0.28, (openAbove ? above : below) - 104)));
    };
    positionPicker();
    window.addEventListener('resize', positionPicker);
    const dialog = dialogRef.current;
    dialog?.addEventListener('scroll', positionPicker);
    const dismiss = (event: PointerEvent) => {
      if (!callerPickerRef.current?.contains(event.target as Node)) setIsCallerPickerOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      window.removeEventListener('resize', positionPicker);
      dialog?.removeEventListener('scroll', positionPicker);
    };
  }, [isCallerPickerOpen]);

  useEffect(() => {
    document.getElementById(`simulator-caller-option-${activeCallerIndex}`)?.scrollIntoView({ block: 'nearest' });
  }, [activeCallerIndex]);

  const fetchClinicInfo = useCallback(async () => {
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = {};
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }
      if (orgId) {
        headers['X-Org-Id'] = orgId;
      }
      const endpoint = orgId ? `${API_BASE_URL}/api/v1/org/${orgId}` : `${API_BASE_URL}/api/v1/org/me`;
      const res = await fetch(endpoint, { headers });
      if (res.ok) {
        const data = await res.json();
        setClinicDetails({
          name: data.name || 'Healthcare Clinic',
          leadDoctor: data.lead_doctor_name || 'Chief Medical Officer',
          specialty: data.clinic_specialty || 'General Practice',
          phone: data.phone || data.hotline || 'Clinic number not configured',
        });
      }

      const allowanceRes = await fetch(`${API_BASE_URL}/api/v1/voice/allowance`, { headers });
      if (allowanceRes.ok) {
        const allowanceData = await allowanceRes.json();
        setVoiceAllowance(allowanceData);
        setAllowanceStatus('ready');
      } else {
        setAllowanceStatus('error');
      }
    } catch {
      setAllowanceStatus('error');
    }
  }, [orgId]);

  const endLiveCallRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!isOpen) {
      endLiveCallRef.current?.();
      return;
    }

    setVoiceAllowance(null);
    setAllowanceStatus('loading');
    void fetchClinicInfo();
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
    void flushQueuedSimulatorFailures();
  }, [isOpen, orgId, fetchClinicInfo]);

  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (callState === 'connected') {
      timer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - (callStartedAtRef.current ?? Date.now())) / 1000);
        setCallSeconds(Math.min(elapsed, sessionLimit));
        if (elapsed >= sessionLimit) {
          setLimitReached(true);
          void endLiveCallRef.current?.();
        }
      }, 1000);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [callState, sessionLimit]);

  useEffect(() => {
    if (callState !== 'connected') return;
    const interval = setInterval(refreshCallResults, 5000);
    return () => clearInterval(interval);
  }, [callState, refreshCallResults]);

  useEffect(() => {
    const flushPendingFailures = () => { void flushQueuedSimulatorFailures(); };
    window.addEventListener('online', flushPendingFailures);
    return () => window.removeEventListener('online', flushPendingFailures);
  }, []);

  useEffect(() => {
    const endOnExit = () => { void endLiveCallRef.current?.(); };
    window.addEventListener('pagehide', endOnExit);
    return () => {
      window.removeEventListener('pagehide', endOnExit);
      endOnExit();
    };
  }, []);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatLog]);


  function startRingingSound() {
    try {
      stopRingingSound();
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      ringAudioCtxRef.current = ctx;

      let isRunning = true;
      let timeoutId: any = null;

      const playBurst = () => {
        if (!isRunning || ctx.state === 'closed') return;
        try {
          const osc1 = ctx.createOscillator();
          const osc2 = ctx.createOscillator();
          const gain = ctx.createGain();

          osc1.type = 'sine';
          osc2.type = 'sine';
          osc1.frequency.value = 440;
          osc2.frequency.value = 480;

          gain.gain.setValueAtTime(0.03, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.6);

          osc1.connect(gain);
          osc2.connect(gain);
          gain.connect(ctx.destination);

          osc1.start();
          osc2.start();
          osc1.stop(ctx.currentTime + 1.6);
          osc2.stop(ctx.currentTime + 1.6);
        } catch { }

        timeoutId = setTimeout(playBurst, 3500);
      };

      playBurst();

      ringOscillatorRef.current = {
        stop: () => {
          isRunning = false;
          if (timeoutId) clearTimeout(timeoutId);
          try {
            ctx.close();
          } catch { }
        },
      };
    } catch { }
  }

  function stopRingingSound() {
    if (ringOscillatorRef.current) {
      ringOscillatorRef.current.stop();
      ringOscillatorRef.current = null;
    }
    ringAudioCtxRef.current = null;
  }

  async function startLiveCall() {
    if (roomRef.current || !orgId || !canStartCall) return;
    const attempt = ++callAttemptRef.current;
    setErrorMsg(null);
    setChatLog([]);
    segmentMapRef.current.clear();
    setCallSeconds(0);
    setLimitReached(false);
    setSessionLimit(Math.min(configuredCallLimit, voiceAllowance?.remaining_seconds ?? configuredCallLimit));
    callStartedAtRef.current = null;
    setIsMuted(false);
    setCallState('dialing');
    roomNameRef.current = null;
    simulatorEndReasonRef.current = 'caller_abandoned';

    try {
      // Obtain permission before reserving clinic time or connecting an agent.
      const microphone = await createLocalAudioTrack({
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      });
      if (attempt !== callAttemptRef.current) {
        microphone.stop();
        return;
      }
      microphoneRef.current = microphone;
      const room = new Room();
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: any) => {
        if (attempt !== callAttemptRef.current || roomRef.current !== room) return;
        if (track.kind === 'audio') {
          const element = track.attach();
          element.id = `livekit-audio-${track.sid || Date.now()}`;
          document.body.appendChild(element);
        }
        stopRingingSound();
        if (callStartedAtRef.current === null) callStartedAtRef.current = Date.now();
        setCallState('connected');
      });

      room.on(RoomEvent.TrackUnsubscribed, (track: any) => {
        if (track.kind === 'audio') {
          track.detach().forEach((el: HTMLElement) => el.remove());
        }
      });

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
        if (attempt !== callAttemptRef.current || roomRef.current !== room) return;
        const isAgent = speakers.some((s) => s.identity.includes('agent'));
        setIsAiSpeaking(isAgent);
      });

      room.on(RoomEvent.TranscriptionReceived, (segments: TranscriptionSegment[], participant?: Participant) => {
        if (attempt !== callAttemptRef.current || roomRef.current !== room) return;
        const isAgent = participant?.identity.includes('agent');
        const sender: 'ai' | 'user' = isAgent ? 'ai' : 'user';
        const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        for (const seg of segments) {
          const text = seg.text?.trim();
          if (!text) continue;

          segmentMapRef.current.set(seg.id, {
            sender,
            text,
            final: seg.final,
            timestamp: nowTime,
          });
        }

        const turns: ChatTurn[] = [];
        segmentMapRef.current.forEach((val) => {
          const lastTurn = turns[turns.length - 1];
          if (lastTurn && lastTurn.sender === val.sender) {
            lastTurn.text = `${lastTurn.text} ${val.text}`.trim();
          } else {
            turns.push({
              sender: val.sender,
              text: val.text,
              timestamp: val.timestamp,
            });
          }
        });

        setChatLog(turns);
      });

      room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        if (attempt !== callAttemptRef.current || roomRef.current !== room) return;
        try {
          const str = new TextDecoder().decode(payload);
          const data = JSON.parse(str);
          if (data.type === 'line_busy') {
            stopRingingSound();
            setErrorMsg(sanitizeErrorMessage('line_busy'));
            simulatorEndReasonRef.current = 'line_busy';
            endLiveCall();
          }
        } catch { }
      });

      room.on(RoomEvent.Disconnected, () => {
        if (attempt !== callAttemptRef.current || roomRef.current !== room) return;
        callAttemptRef.current += 1;
        if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
        roomRef.current = null;
        roomNameRef.current = null;
        stopRingingSound();
        setIsAiSpeaking(false);
        void refreshClinicPatients();
        refreshCallResults();
        setCallState((current) => (current === 'connected' ? 'ended' : 'idle'));
        microphoneRef.current?.stop();
        void fetchClinicInfo();
      });

      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`;
      }
      if (orgId) {
        headers['X-Org-Id'] = orgId;
      }

      const res = await fetch(`${API_BASE_URL}/api/v1/voice/simulator/start`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          caller_phone: callerPhone,
          caller_name: simulatorCallerName,
        }),
      });

      if (!res.ok) {
        const failure = await res.json().catch(() => null);
        if (res.status === 402 || failure?.detail?.code === 'VOICE_DEMO_LIMIT_REACHED') {
          throw new Error('This clinic has used its available voice minutes.');
        }
        if (res.status === 409) {
          throw new Error('This clinic already has a call connecting or in progress.');
        }
        if (res.status === 429) {
          throw new Error('The demo voice line is busy. Please try again in a moment.');
        }
        throw new Error(typeof failure?.detail === 'string' ? failure.detail : 'Unable to connect to the clinic phone system. Please verify network or server status.');
      }

      const data = await res.json();
      if (attempt !== callAttemptRef.current) {
        void queueSimulatorFailure({
          org_id: orgId, room_name: data.room_name,
          caller_phone: callerPhone, caller_name: simulatorCallerName, call_outcome: 'caller_abandoned'
        });
        return;
      }
      roomNameRef.current = data.room_name || null;
      if (typeof data.call_budget_seconds === 'number' && data.call_budget_seconds > 0) {
        setSessionLimit(Math.min(configuredCallLimit, data.call_budget_seconds));
      }
      void fetchClinicInfo();
      const connectPromise = room.connect(data.server_url, data.token);
      const timeoutPromise = new Promise((_, reject) =>
        connectTimerRef.current = setTimeout(() => reject(new Error('Connection timed out. The voice assistant took too long to answer.')), 15000)
      );

      await Promise.race([connectPromise, timeoutPromise]);
      if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
      if (attempt !== callAttemptRef.current) return;

      setCallState((current) => current === 'connected' ? current : 'ringing');
      // Audio can arrive before connect() resolves; don't restart ringing over it.
      if (!Array.from(room.remoteParticipants.values()).some(participant =>
        Array.from(participant.audioTrackPublications.values()).some(publication => publication.isSubscribed)
      )) startRingingSound();

      if (microphoneRef.current) await room.localParticipant.publishTrack(microphoneRef.current);
    } catch (err: any) {
      if (attempt !== callAttemptRef.current) return;
      stopRingingSound();
      if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
      microphoneRef.current?.stop();
      if (orgId && roomNameRef.current) {
        void queueSimulatorFailure({
          org_id: orgId,
          room_name: roomNameRef.current,
          caller_phone: callerPhone,
          caller_name: simulatorCallerName,
          call_outcome: 'service_unavailable',
        });
      }
      if (roomRef.current) {
        const failedRoom = roomRef.current;
        roomRef.current = null;
        void failedRoom.disconnect().catch(() => { });
      }
      setErrorMsg(sanitizeErrorMessage(err.message));
      setCallState('idle');
    }
  }

  async function toggleMute() {
    if (!microphoneRef.current) return;
    try {
      const nextMuted = !isMuted;
      if (nextMuted) {
        await microphoneRef.current.mute();
      } else {
        await microphoneRef.current.unmute();
      }
      setIsMuted(nextMuted);
    } catch { }
  }

  async function endLiveCall() {
    callAttemptRef.current += 1;
    if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
    microphoneRef.current?.stop();
    stopRingingSound();

    let settlement: Promise<void> | undefined;
    if (roomNameRef.current && orgId) {
      settlement = queueSimulatorFailure({
        org_id: orgId,
        room_name: roomNameRef.current,
        caller_phone: callerPhone,
        caller_name: simulatorCallerName,
        call_outcome: simulatorEndReasonRef.current,
      });
      simulatorEndReasonRef.current = 'caller_abandoned';
    }

    if (roomRef.current) {
      const endingRoom = roomRef.current;
      roomRef.current = null;
      void endingRoom.disconnect().catch(() => { });
    }
    roomNameRef.current = null;

    document.querySelectorAll('[id^="livekit-audio-"]').forEach((el) => el.remove());

    setIsAiSpeaking(false);
    refreshCallResults();
    // Refresh after the server releases reserved time, so the balance is current.
    void (settlement ?? Promise.resolve()).then(fetchClinicInfo);
    if (callState === 'connected') {
      setCallState('ended');
    } else {
      setCallState('idle');
    }
  }

  endLiveCallRef.current = endLiveCall;

  function formatTimer(totalSeconds: number) {
    const mins = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const secs = (totalSeconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  }

  if (!isOpen) return null;

  const quotaPercent = voiceAllowance && voiceAllowance.limit_seconds > 0
    ? Math.min(100, Math.max(0, voiceAllowance.remaining_seconds / voiceAllowance.limit_seconds * 100)) : 0;
  const inputClass = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#BFDDCD] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0D2622]";
  const closeSimulator = () => {
    void endLiveCall();
    onClose();
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="voice-simulator-title"
      aria-describedby="voice-simulator-description"
      onCancel={(event) => { event.preventDefault(); closeSimulator(); }}
      className="m-auto w-[calc(100%-24px)] max-w-[860px] max-h-[92dvh] overflow-y-auto sm:open:flex sm:flex-col sm:h-[min(640px,calc(100dvh-32px))] sm:max-h-none sm:overflow-hidden rounded-[28px] border border-white/15 bg-[#0D2622] p-0 text-[#F1F4EE] shadow-2xl backdrop:bg-[#061713]/75 backdrop:backdrop-blur-sm"
    >
      <header className="flex items-center justify-between shrink-0 gap-3 border-b border-white/10 px-5 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#BFDDCD]/20 bg-[#1E6B56]/30 text-[#BFDDCD]">
            <Headphones className="h-5 w-5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="voice-simulator-title" className="text-base font-semibold tracking-tight">Voice simulator</h2>
              <span className="rounded-md border border-[#BFDDCD]/20 bg-[#BFDDCD]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#BFDDCD]">Demo</span>
            </div>
            <p id="voice-simulator-description" className="mt-0.5 text-xs text-[#A8BEB6]">Experience your AI receptionist, live.</p>
          </div>
        </div>
        <button type="button" onClick={closeSimulator} aria-label="Close voice simulator" className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#A8BEB6] transition hover:bg-white/10 hover:text-white ${inputClass}`}>
          <X className="h-5 w-5" />
        </button>
      </header>

      <div className="grid min-h-0 sm:flex-1 sm:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="space-y-4 border-b border-white/10 bg-[#143530]/45 p-5 sm:border-b-0 sm:border-r sm:p-5">
          <div className="flex items-start gap-3">
            <Building2 className="mt-0.5 h-5 w-5 shrink-0 text-[#BFDDCD]" />
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#A8BEB6]">Your reception desk</p>
              <h3 className="mt-1 break-words text-sm font-semibold">{clinicDetails?.name || 'Healthcare Clinic'}</h3>
              {clinicDetails?.specialty && <p className="mt-1 text-xs text-[#A8BEB6]">{clinicDetails.specialty}</p>}
            </div>
          </div>

          <section aria-label="Demo voice quota" className="rounded-2xl border border-[#BFDDCD]/15 bg-[#0D2622] p-4">
            <div className="flex items-center justify-between gap-2 text-xs text-[#A8BEB6]">
              <span>Demo quota remaining</span><Clock className="h-3.5 w-3.5" />
            </div>
            {allowanceStatus === 'loading' ? (
              <p role="status" className="py-4 text-sm text-[#BFDDCD]">Checking allowance…</p>
            ) : allowanceStatus === 'error' ? (
              <div className="mt-3 text-xs text-amber-200">
                <p>Couldn’t load the demo quota.</p>
                <button type="button" onClick={() => { setAllowanceStatus('loading'); void fetchClinicInfo(); }} className={`mt-2 inline-flex min-h-8 items-center gap-1.5 rounded-md underline underline-offset-4 ${inputClass}`}><RefreshCw className="h-3 w-3" /> Refresh quota</button>
              </div>
            ) : voiceAllowance && (
              <>
                <p className={`mt-2 font-mono text-3xl font-semibold tabular-nums tracking-tight ${quotaExhausted ? 'text-amber-200' : 'text-[#D5EAD9]'}`}>
                  {formatTimer(voiceAllowance.remaining_seconds)}<span className="ml-1.5 font-sans text-xs font-normal tracking-normal text-[#A8BEB6]">min:sec</span>
                </p>
                <div role="meter" aria-label="Remaining demo quota" aria-valuemin={0} aria-valuemax={voiceAllowance.limit_seconds} aria-valuenow={voiceAllowance.remaining_seconds} className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-[#BFDDCD] transition-[width]" style={{ width: `${quotaPercent}%` }} />
                </div>
                <p className="mt-2 text-xs text-[#A8BEB6]">{formatTimer(voiceAllowance.limit_seconds)} total · shared by this clinic</p>
                <p className="mt-2 border-t border-white/10 pt-2 text-xs leading-relaxed text-[#A8BEB6]">
                  {quotaExhausted ? 'No minutes available for a new call. Ask your administrator for more demo time.' : isCalling ? 'Time is reserved while a call is active. The balance refreshes after it ends.' : 'Available for new calls; active calls reserve time.'}
                </p>
              </>
            )}
          </section>

          <div className="flex items-start gap-2.5 text-xs leading-relaxed">
            <Clock className="mt-0.5 h-4 w-4 shrink-0 text-[#BFDDCD]" />
            <div><p className="font-semibold text-[#D5EAD9]">{formatTimer(configuredCallLimit)} maximum per call</p>
              <p className="mt-1 text-[#A8BEB6]">Calls end automatically at the limit, or earlier if your remaining quota runs out.</p></div>
          </div>

          {!isCalling && !quotaExhausted && <div className="hidden border-t border-white/10 pt-3 sm:block [@media(max-height:680px)]:hidden">
            <p className="flex items-center gap-2 text-xs font-semibold text-[#D5EAD9]"><Sparkles className="h-3.5 w-3.5" /> Try a conversation</p>
            <div className="mt-2 space-y-2 text-xs leading-relaxed text-[#A8BEB6]">
              <p>“I’d like to book an appointment.”</p>
              <p>“What are your clinic hours?”</p>
            </div>
            <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-[#A8BEB6]"><ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-[#BFDDCD]" /> Confirmed bookings appear on your clinic dashboard.</p>
          </div>}
        </aside>

        <main className="flex min-h-0 min-w-0 flex-col p-5 sm:p-5">
          {errorMsg && (
            <div role="alert" className="mb-3 shrink-0 flex items-start gap-2.5 rounded-xl border border-amber-300/25 bg-amber-300/10 p-3 text-xs leading-relaxed text-amber-100">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <div><p className="font-semibold">Unable to complete the call</p><p className="mt-1">{errorMsg}</p></div>
            </div>
          )}

          {callState === 'idle' && (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#BFDDCD]">Make a test call</p>
                <h3 className="mt-1 text-xl font-semibold tracking-tight">Meet your receptionist.</h3>
                <p className="mt-1 text-sm leading-relaxed text-[#A8BEB6]">Speak naturally to book a visit, ask a question, or try a returning patient’s experience.</p>
              </div>
              <p className="flex items-center gap-2 text-xs text-[#A8BEB6]"><Mic className="h-3.5 w-3.5 shrink-0 text-[#BFDDCD]" /> Browser call · Microphone &amp; speakers</p>
              <div className="grid gap-3 sm:grid-cols-2 p-3 rounded-2xl bg-[#143530]/70 border border-[rgba(241,244,238,0.12)]">
                <div
                  ref={callerPickerRef}
                  className="relative space-y-2 sm:col-span-2"
                  onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setIsCallerPickerOpen(false); }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape' && isCallerPickerOpen) {
                      event.preventDefault();
                      event.stopPropagation();
                      setIsCallerPickerOpen(false);
                      callerPickerButtonRef.current?.focus();
                    }
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <label id="simulator-caller-label" className="text-[11px] font-semibold uppercase tracking-wider text-[#A8BEB6]">Calling as</label>
                    <span className="text-[10px] text-[#A8BEB6]">{needsCallerSelection ? 'Shared contact number' : matchedPatient ? 'Returning patient' : 'New caller'}</span>
                  </div>
                  <button
                    ref={callerPickerButtonRef}
                    type="button"
                    aria-labelledby="simulator-caller-label simulator-caller-value"
                    aria-haspopup="listbox"
                    aria-expanded={isCallerPickerOpen}
                    aria-controls="simulator-caller-options"
                    onClick={() => { setIsCallerPickerOpen(!isCallerPickerOpen); setCallerSearch(''); setActiveCallerIndex(0); }}
                    className={`flex min-h-14 w-full items-center gap-3 rounded-xl border bg-[#0D2622] px-3 py-2 text-left transition hover:border-[#BFDDCD]/50 ${isCallerPickerOpen ? 'border-[#BFDDCD]/60' : 'border-white/15'} ${inputClass}`}
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#BFDDCD]/10 text-[#BFDDCD]"><UserRound className="h-4 w-4" /></span>
                    <span id="simulator-caller-value" className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{needsCallerSelection ? 'Choose the patient calling' : matchedPatient?.name || callerName || 'New demo caller'}</span>
                      <span className="mt-0.5 block truncate text-xs text-[#A8BEB6]">{needsCallerSelection ? `${phoneMatches.length} patients share this number` : matchedPatient ? matchedPatient.phone : 'Enter details or choose a saved patient'}</span>
                    </span>
                    <ChevronDown className={`h-4 w-4 shrink-0 text-[#A8BEB6] transition-transform ${isCallerPickerOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {isCallerPickerOpen && (
                    <div className={`absolute inset-x-0 z-20 overflow-hidden rounded-xl border border-[#BFDDCD]/25 bg-[#102D27] shadow-[0_16px_40px_rgba(0,0,0,0.5)] ${callerPickerPlacement === 'above' ? 'bottom-full mb-2' : 'top-full mt-2'}`}>
                      <div className="relative m-2">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#A8BEB6]" />
                        <input
                          ref={callerSearchRef}
                          type="text"
                          role="combobox"
                          aria-label="Search saved callers"
                          aria-expanded="true"
                          aria-autocomplete="list"
                          aria-controls="simulator-caller-options"
                          aria-activedescendant={`simulator-caller-option-${activeCallerIndex}`}
                          value={callerSearch}
                          onChange={(event) => { setCallerSearch(event.target.value); setActiveCallerIndex(0); }}
                          onKeyDown={(event) => {
                            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                              event.preventDefault();
                              setActiveCallerIndex((index) => (index + (event.key === 'ArrowDown' ? 1 : -1) + filteredCallerProfiles.length + 1) % (filteredCallerProfiles.length + 1));
                            } else if (event.key === 'Enter') {
                              event.preventDefault();
                              chooseCaller(activeCallerIndex === 0 ? undefined : filteredCallerProfiles[activeCallerIndex - 1]);
                            } else if (event.key === 'Tab') setIsCallerPickerOpen(false);
                          }}
                          placeholder="Search by name or phone"
                          className={`h-10 w-full rounded-lg border border-white/10 bg-[#0D2622] pl-9 pr-3 text-xs text-white placeholder:text-[#A8BEB6] ${inputClass}`}
                        />
                      </div>
                      <div id="simulator-caller-options" role="listbox" aria-label="Caller profiles" style={{ maxHeight: callerOptionsHeight }} className="overflow-y-auto overscroll-contain p-1.5 pt-0">
                        <button id="simulator-caller-option-0" type="button" role="option" tabIndex={-1} aria-selected={!matchedPatient} onClick={() => chooseCaller()} className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left ${activeCallerIndex === 0 ? 'bg-[#BFDDCD]/15' : 'hover:bg-white/5'}`}>
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-dashed border-[#BFDDCD]/30 text-[#BFDDCD]"><Plus className="h-4 w-4" /></span>
                          <span className="min-w-0 flex-1"><span className="block text-xs font-semibold">Use a new caller</span><span className="block text-[11px] text-[#A8BEB6]">Try a first-time patient conversation</span></span>
                          {!matchedPatient && <Check className="h-4 w-4 shrink-0 text-[#BFDDCD]" />}
                        </button>
                        {filteredCallerProfiles.map((patient, index) => (
                          <button key={patient.id} id={`simulator-caller-option-${index + 1}`} type="button" role="option" tabIndex={-1} aria-selected={matchedPatient?.id === patient.id} onClick={() => chooseCaller(patient)} className={`mt-1 flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left ${activeCallerIndex === index + 1 ? 'bg-[#BFDDCD]/15' : 'hover:bg-white/5'}`}>
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#BFDDCD]/10 text-xs font-semibold text-[#BFDDCD]">{patient.name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('')}</span>
                            <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{patient.name}</span><span className="mt-0.5 block truncate text-[11px] text-[#A8BEB6]">{patient.phone} · {patient.total_visits} {patient.total_visits === 1 ? 'visit' : 'visits'}</span></span>
                            {matchedPatient?.id === patient.id && <Check className="h-4 w-4 shrink-0 text-[#BFDDCD]" />}
                          </button>
                        ))}
                      </div>
                      <p role="status" className="border-t border-white/10 px-3 py-2 text-[10px] text-[#A8BEB6]">{savedCallerProfiles.length === 0 ? 'No saved patients yet. Use a new caller to try the demo.' : filteredCallerProfiles.length === 0 ? 'No matching patients. Try another name or use a new caller.' : `${filteredCallerProfiles.length} saved ${filteredCallerProfiles.length === 1 ? 'patient' : 'patients'} · ↑↓ to browse · Enter to select`}</p>
                    </div>
                  )}
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="voice-simulator-phone" className="text-xs font-medium text-[rgba(241,244,238,0.5)] block">
                    Phone number
                  </label>
                  <input
                    id="voice-simulator-phone"
                    type="tel"
                    autoComplete="tel"
                    value={callerPhone}
                    onChange={(event) => {
                      const nextPhone = event.target.value;
                      callerIdentityEditedRef.current = true;
                      setSelectedCallerId(null);
                      setCallerPhone(nextPhone);
                      setCallerName('');
                    }}
                    placeholder="+91 98765 43210"
                    className="w-full bg-[#0D2622] border border-[rgba(241,244,238,0.15)] rounded-xl px-3.5 py-2 text-sm font-mono text-white focus:outline-none focus:border-[#1E6B56] focus:ring-1 focus:ring-[#1E6B56] transition"
                  />
                </div>

                {matchedPatient ? (
                  <div className="flex items-start gap-2.5 self-end rounded-xl bg-[#1E6B56]/20 border border-[#1E6B56]/40 p-2.5">
                    <BadgeCheck className="w-4 h-4 text-[#BFDDCD] shrink-0 mt-0.5" />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[#BFDDCD]">Patient recognized · {matchedPatient.total_visits} {matchedPatient.total_visits === 1 ? 'visit' : 'visits'}</p>
                      <p className="text-xs text-[#BFDDCD]/70 mt-0.5">
                        Last visit {matchedPatient.last_visit}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <label htmlFor="voice-simulator-name" className="text-xs font-medium text-[rgba(241,244,238,0.5)] block">
                      Caller name
                    </label>
                    <div className="relative">
                      <UserRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[rgba(241,244,238,0.4)]" />
                      <input
                        id="voice-simulator-name"
                        type="text"
                        autoComplete="name"
                        value={callerName}
                        onChange={(event) => {
                          callerIdentityEditedRef.current = true;
                          setCallerName(event.target.value);
                        }}
                        placeholder="Name for a new caller"
                        className="w-full bg-[#0D2622] border border-[rgba(241,244,238,0.15)] rounded-xl pl-9 pr-3.5 py-2 text-sm text-white focus:outline-none focus:border-[#1E6B56] focus:ring-1 focus:ring-[#1E6B56] transition"
                      />
                    </div>
                    <p className="text-xs text-[rgba(241,244,238,0.5)] leading-relaxed">
                      A patient profile is created when an appointment or walk-in is saved.
                    </p>
                  </div>
                )}
              </div>
              <div className="mt-auto shrink-0 space-y-2 pt-1">
                <button type="button" onClick={startLiveCall} disabled={!canStartCall} className={`flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#C9E6CA] px-4 py-3 text-sm font-semibold text-[#0D2622] transition hover:bg-[#DDF0DD] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-[#A8BEB6] ${inputClass}`}>
                  <PhoneCall className="h-4 w-4" /><span>{quotaExhausted ? 'Demo quota unavailable' : allowanceStatus === 'loading' ? 'Checking demo quota…' : 'Call Clinic Reception'}</span>
                </button>
                <p className="text-center text-xs leading-relaxed text-[#A8BEB6]">Allow microphone access to begin. Calls are recorded.<br />Use fictional details; demo bookings are saved.</p>
              </div>
            </div>
          )}

          {isCalling && (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div className="shrink-0 text-center">
                <p role="status" className="inline-flex items-center gap-2 rounded-full border border-[#BFDDCD]/20 bg-[#BFDDCD]/5 px-3 py-1.5 text-xs text-[#BFDDCD]">
                  <span className={`h-1.5 w-1.5 rounded-full bg-current ${callState !== 'connected' ? 'motion-safe:animate-pulse' : ''}`} />
                  {callState === 'connected' ? 'Call in progress' : callState === 'dialing' ? 'Preparing your call' : 'Ringing reception'}
                </p>
                <div className={`mx-auto mt-3 flex h-14 w-14 items-center justify-center rounded-full border transition-all duration-150 [@media(max-height:680px)]:hidden ${
                  callState !== 'connected'
                    ? 'border-[#BFDDCD]/25 bg-[#1E6B56]/30 text-[#BFDDCD]'
                    : isAiSpeaking
                    ? 'border-[#BFDDCD]/40 bg-[#1E6B56]/40 text-[#BFDDCD] shadow-[0_0_0_12px_rgba(191,221,205,0.08)]'
                    : isMuted
                    ? 'border-amber-400/30 bg-amber-500/10 text-amber-300'
                    : 'border-[#BFDDCD]/25 bg-[#1E6B56]/30 text-[#BFDDCD]'
                }`}>
                  {callState !== 'connected' ? (
                    <PhoneCall className="h-7 w-7 motion-safe:animate-pulse" />
                  ) : isAiSpeaking ? (
                    <Volume2 className="h-8 w-8" />
                  ) : isMuted ? (
                    <MicOff className="h-7 w-7" />
                  ) : <Mic className="h-7 w-7" />}
                </div>
                <h3 className="mt-3 text-lg font-semibold">{clinicDetails?.name || 'Clinic receptionist'}</h3>
                <p role="status" className="mt-1 text-sm text-[#A8BEB6]">
                  {callState !== 'connected'
                    ? 'Connecting to your AI receptionist…'
                    : isAiSpeaking
                    ? 'Receptionist is speaking'
                    : isMuted
                    ? 'Your microphone is muted'
                    : 'Listening to you…'}
                </p>
                <p className="mt-2 text-xs text-[#A8BEB6]">Calling as {simulatorCallerName}</p>
              </div>

              {callState === 'connected' && (
                <p role="status" aria-label="Call time remaining" className={`mx-auto shrink-0 rounded-full border px-3 py-1 font-mono text-xs font-semibold tabular-nums ${isNearCallLimit ? 'border-amber-300/30 bg-amber-300/10 text-amber-100' : 'border-white/10 bg-[#143530]/50 text-[#D5EAD9]'}`}>
                  {formatTimer(remainingCallSeconds)} left
                </p>
              )}

              {callState === 'connected' && (
                <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-white/10">
                  <button type="button" aria-expanded={showTranscript} aria-controls="simulator-transcript" onClick={() => setShowTranscript(!showTranscript)} className={`flex min-h-11 w-full items-center justify-between gap-2 px-3 text-xs font-medium text-[#D5EAD9] hover:bg-white/5 ${inputClass}`}>
                    <span className="flex items-center gap-2"><MessageSquare className="h-4 w-4" /> Live transcript</span>{showTranscript ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                  {showTranscript && <div id="simulator-transcript" ref={chatScrollRef} role="log" aria-label="Call transcript" aria-live="polite" className="min-h-0 max-h-44 flex-1 space-y-3 overflow-y-auto sm:max-h-none border-t border-white/10 p-3">
                    {chatLog.length === 0 ? <p className="py-4 text-center text-xs text-[#A8BEB6]">Your conversation will appear here.</p> : chatLog.map((turn, i) => (
                      <div key={i} className={`rounded-lg p-3 ${turn.sender === 'ai' ? 'mr-4 bg-[#1E6B56]/25' : 'ml-4 bg-white/5'}`}>
                        <div className="mb-1 flex items-center justify-between gap-2 text-[10px] text-[#A8BEB6]"><span className="font-semibold">{turn.sender === 'ai' ? 'Receptionist' : 'You'}</span><span>{turn.timestamp}</span></div>
                        <p className="text-xs leading-relaxed">{turn.text}</p>
                      </div>
                    ))}
                  </div>}
                </section>
              )}

              <div className="mt-auto flex shrink-0 items-center justify-center gap-3 border-t border-white/10 pt-3">
                {callState === 'connected' && <button type="button" onClick={toggleMute} aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'} aria-pressed={isMuted} className={`flex min-h-12 items-center gap-2 rounded-xl border px-4 text-sm font-medium transition ${inputClass} ${isMuted ? 'border-amber-200/40 bg-amber-200/15 text-amber-100' : 'border-white/15 text-[#D5EAD9] hover:bg-white/5'}`}>
                  {isMuted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}{isMuted ? 'Unmute' : 'Mute'}
                </button>}
                <button type="button" onClick={endLiveCall} aria-label="End Call" className={`flex min-h-12 items-center justify-center gap-2 rounded-xl bg-rose-500/90 px-5 text-sm font-semibold text-white transition hover:bg-rose-500 ${inputClass}`}><PhoneOff className="h-4 w-4" />{callState === 'connected' ? 'End call' : 'Cancel call'}</button>
              </div>
            </div>
          )}

          {callState === 'ended' && (
            <div className="flex flex-1 flex-col items-center justify-center gap-5 py-6 text-center">
              <span className="flex h-16 w-16 items-center justify-center rounded-full border border-[#BFDDCD]/20 bg-[#1E6B56]/25 text-[#BFDDCD]"><Check className="h-7 w-7" /></span>
              <div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#BFDDCD]">Demo complete</p><h3 className="mt-2 text-2xl font-semibold">Call ended</h3><p className="mt-2 text-sm text-[#A8BEB6]">{limitReached || callSeconds >= sessionLimit ? `The ${formatTimer(sessionLimit)} demo call limit was reached.` : 'Thanks for trying your AI receptionist.'}</p></div>
              <div className="w-full rounded-xl border border-white/10 bg-[#143530]/50 p-4"><p className="text-xs text-[#A8BEB6]">Call duration</p><p className="mt-1 font-mono text-3xl tabular-nums text-[#D5EAD9]">{formatTimer(callSeconds)}</p></div>
              <p className="text-xs leading-relaxed text-[#A8BEB6]">Any bookings or patient updates made during this call appear on your clinic dashboard.</p>
              <div className="mt-2 flex w-full flex-wrap justify-center gap-3">
                <button type="button" onClick={() => { setCallState('idle'); setCallSeconds(0); setChatLog([]); }} className={`flex min-h-11 items-center gap-2 rounded-xl border border-white/15 px-4 text-sm hover:bg-white/5 ${inputClass}`}><RefreshCw className="h-4 w-4" /> Back to call setup</button>
                <button type="button" onClick={closeSimulator} className={`min-h-11 rounded-xl bg-[#C9E6CA] px-6 text-sm font-semibold text-[#0D2622] hover:bg-[#DDF0DD] ${inputClass}`}>Done</button>
              </div>
            </div>
          )}
        </main>
      </div>
    </dialog>
  );
}
