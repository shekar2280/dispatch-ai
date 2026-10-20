'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { httpClient } from '@/lib/api/httpClient';
import { useClinicStore } from '../store';
import { ClinicClosureItem } from '../types';

export const SCHEDULE_HISTORY_PREVIEW_LIMIT = 3;

function localCreatedAt(id: string, fallback: string): string {
  const timestamp = Number(id.split('-')[1]);
  return Number.isFinite(timestamp) && timestamp > 0 ? new Date(timestamp).toISOString() : fallback;
}

export function useScheduleHistory(enabled = true) {
  const orgId = useClinicStore((s) => s.orgId);
  const localLeaves = useClinicStore((s) => s.leaves);
  const dateOverrides = useClinicStore((s) => s.dateOverrides);
  const query = useQuery({
    queryKey: ['clinic-closures', orgId],
    queryFn: () => httpClient.get<ClinicClosureItem[]>(`/api/v1/org/${orgId}/closures`, { orgId }),
    enabled: Boolean(orgId) && enabled,
  });
  const apiClosures = query.data;

  const allItems = useMemo(() => {
    const list: Array<{
      id: string;
      type: 'leave' | 'special_hours' | 'emergency_closure';
      title: string;
      startDate: string;
      endDate: string;
      customHours?: Array<{ name?: string; start: string; end: string }> | null;
      reason?: string | null;
      isApi: boolean;
      createdAt: string;
      emergencyPhone?: string | null;
      doctorId?: string | null;
    }> = [];

    (apiClosures || []).forEach((c) => {
      const t = c.override_type === 'special_hours' ? 'special_hours' : c.override_type === 'emergency_closure' ? 'emergency_closure' : 'leave';
      list.push({
        id: c.id,
        type: t,
        title: c.title,
        startDate: c.start_date,
        endDate: c.end_date,
        customHours: c.custom_hours,
        reason: c.reason,
        emergencyPhone: c.emergency_phone,
        doctorId: c.doctor_id,
        isApi: true,
        createdAt: c.created_at || c.start_date,
      });
    });

    (orgId ? [] : localLeaves).forEach((l) => {
      if (!list.some((item) => item.startDate === l.startDate && item.endDate === l.endDate && item.type === 'leave')) {
        list.push({
          id: l.id,
          createdAt: localCreatedAt(l.id, l.startDate),
          type: 'leave',
          title: l.reason,
          startDate: l.startDate,
          endDate: l.endDate,
          reason: l.reason,
          isApi: false,
        });
      }
    });

    (orgId ? [] : dateOverrides).forEach((o) => {
      if (!list.some((item) => item.startDate === o.date && (item.type === 'special_hours' || item.type === 'emergency_closure'))) {
        list.push({
          id: o.id,
          createdAt: localCreatedAt(o.id, o.date),
          type: o.overrideType === 'closed_special' ? 'emergency_closure' : 'special_hours',
          title: o.reason || (o.overrideType === 'open_special' ? 'Special Open Shift' : 'Closed'),
          startDate: o.date,
          endDate: o.date,
          customHours: o.overrideType === 'open_special' && o.morningStart && o.morningEnd ? [{ name: 'Shift', start: o.morningStart, end: o.morningEnd }] : null,
          reason: o.reason,
          isApi: false,
        });
      }
    });

    return list.sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.startDate.localeCompare(a.startDate));
  }, [apiClosures, localLeaves, dateOverrides, orgId]);


  return { ...query, items: allItems };
}
