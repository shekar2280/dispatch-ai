'use client';

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createClient } from '@/lib/supabase/client';
import { API_ROUTES } from '@/lib/constants';
import { clinicQueryKeys } from '../../_hooks/useClinicQueries';

export function useCallEvents(orgId?: string | null) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!orgId) return;
    let closed = false;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let heartbeat: ReturnType<typeof setInterval> | undefined;
    let invalidation: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let generation = 0;

    async function connect() {
      const currentGeneration = ++generation;
      const { data } = await createClient().auth.getSession();
      if (closed || currentGeneration !== generation || !data.session?.access_token) return;
      socket = new WebSocket(API_ROUTES.ws.clinic(orgId!));
      socket.onopen = () => {
        socket?.send(JSON.stringify({ type: 'auth', token: data.session.access_token }));
        attempt = 0;
        heartbeat = setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'heartbeat' }));
        }, 20000);
      };
      socket.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data);
          if (!payload.event || invalidation) return;
          invalidation = setTimeout(() => {
            invalidation = undefined;
            void queryClient.invalidateQueries({ queryKey: clinicQueryKeys.calls(orgId) });
            void queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
          }, 200);
        } catch { return; }
      };
      socket.onclose = (event) => {
        if (heartbeat) clearInterval(heartbeat);
        if (closed || event.code === 1008) return;
        retry = setTimeout(() => { void connect(); }, Math.min(30000, 1000 * 2 ** attempt++));
      };
    }
    void connect();
    const { data: listener } = createClient().auth.onAuthStateChange(() => {
      if (closed) return;
      if (retry) clearTimeout(retry);
      if (socket) socket.onclose = null;
      socket?.close();
      if (heartbeat) clearInterval(heartbeat);
      void connect();
    });
    return () => {
      closed = true;
      listener.subscription.unsubscribe();
      if (retry) clearTimeout(retry);
      if (heartbeat) clearInterval(heartbeat);
      if (invalidation) clearTimeout(invalidation);
      socket?.close();
    };
  }, [orgId, queryClient]);
}
