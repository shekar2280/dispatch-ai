import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { httpClient } from "@/lib/api/httpClient";
import { createClient } from "@/lib/supabase/client";
import {
  ClinicLiveDashboardData,
  ClinicDailySlotsResponse,
  ClinicAnalyticsData,
  ClinicRevenueResponse,
  AppointmentItem,
  PatientRecordItem,
  CapacityHourlyBucket,
  VisitEventItem,
  ClinicCallSessionItem,
  ClinicBillingCatalog,
} from "../types";

export const clinicQueryKeys = {
  all: ["clinic"] as const,
  dashboard: (orgId?: string | null) =>
    [...clinicQueryKeys.all, "dashboard", orgId] as const,
  slots: (orgId?: string | null, date?: string | null) =>
    date
      ? ([...clinicQueryKeys.all, "slots", orgId, date] as const)
      : ([...clinicQueryKeys.all, "slots", orgId] as const),
  capacityLedger: (orgId?: string | null, date?: string | null) =>
    date
      ? ([...clinicQueryKeys.all, "capacity-ledger", orgId, date] as const)
      : ([...clinicQueryKeys.all, "capacity-ledger", orgId] as const),
  appointments: (orgId?: string | null, date?: string | null) =>
    date
      ? ([...clinicQueryKeys.all, "appointments", orgId, date] as const)
      : ([...clinicQueryKeys.all, "appointments", orgId] as const),
  queue: (orgId?: string | null) =>
    [...clinicQueryKeys.all, "queue", orgId] as const,
  analytics: (orgId?: string | null, period?: string) =>
    period
      ? ([...clinicQueryKeys.all, "analytics", orgId, period] as const)
      : ([...clinicQueryKeys.all, "analytics", orgId] as const),
  revenue: (orgId?: string | null, period?: string) =>
    period
      ? ([...clinicQueryKeys.all, "revenue", orgId, period] as const)
      : ([...clinicQueryKeys.all, "revenue", orgId] as const),
  patients: (orgId?: string | null) =>
    [...clinicQueryKeys.all, "patients", orgId] as const,
  calls: (orgId?: string | null) =>
    [...clinicQueryKeys.all, "calls", orgId] as const,
  billingCatalog: (orgId?: string | null) =>
    [...clinicQueryKeys.all, "billing-catalog", orgId] as const,
};

export function useClinicBillingCatalogQuery(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: clinicQueryKeys.billingCatalog(orgId),
    queryFn: async ({ signal }) => {
      const raw = await queryClient.fetchQuery({
        queryKey: ["clinic-organization", orgId],
        queryFn: ({ signal }) =>
          httpClient.get<any>(`/api/v1/org/${orgId}`, { orgId, signal }),
        staleTime: 300_000,
      });
      const org = { ...raw, ...raw.booking_settings };
      const configuredVisitTypes = Array.isArray(org.visit_charge_types)
        ? org.visit_charge_types.filter((x: any) => x.active !== false)
        : [];
      return {
        visit_charge_types: configuredVisitTypes,
        billing_catalog: Array.isArray(org.billing_catalog)
          ? org.billing_catalog.filter((x: any) => x.active !== false)
          : [],
        consultation_fee:
          org.consultation_fee == null ? null : Number(org.consultation_fee),
        currency_symbol: raw.currency_symbol || null,
      } as ClinicBillingCatalog;
    },
    enabled: Boolean(orgId),
    staleTime: 60_000,
  });
}

export function useClinicDashboardQuery(orgId?: string | null) {
  return useQuery({
    queryKey: clinicQueryKeys.dashboard(orgId),
    queryFn: ({ signal }) =>
      httpClient.get<ClinicLiveDashboardData>(
        "/api/v1/appointments/dashboard/live",
        { orgId, signal },
      ),
    enabled: Boolean(orgId),
    staleTime: 1000 * 30,
  });
}

export function useClinicSlotsQuery(
  orgId?: string | null,
  dateStr?: string | null,
  doctorId?: string | null,
) {
  return useQuery({
    queryKey: [...clinicQueryKeys.slots(orgId, dateStr || ""), doctorId],
    queryFn: ({ signal }) =>
      httpClient.get<ClinicDailySlotsResponse>("/api/v1/appointments/slots", {
        orgId,
        signal,
        params: {
          target_date: dateStr,
          ...(doctorId ? { doctor_id: doctorId } : {}),
        },
      }),
    enabled: Boolean(orgId) && Boolean(dateStr),
    staleTime: 1000 * 30,
  });
}

export function useClinicCapacityLedgerQuery(
  orgId?: string | null,
  dateStr?: string | null,
) {
  const targetDate = dateStr || new Date().toISOString().split("T")[0];

  return useQuery({
    queryKey: clinicQueryKeys.capacityLedger(orgId, targetDate),
    queryFn: ({ signal }) =>
      httpClient.get<CapacityHourlyBucket[]>(
        "/api/v1/appointments/capacity-ledger",
        {
          orgId,
          signal,
          params: { target_date: targetDate },
        },
      ),
    enabled: Boolean(orgId),
    staleTime: 1000 * 15,
  });
}

export function useClinicAppointmentsQuery(
  orgId?: string | null,
  dateStr?: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: clinicQueryKeys.appointments(orgId, dateStr),
    queryFn: async ({ signal }) => {
      const raw = await httpClient.get<any[]>("/api/v1/appointments/", {
        orgId,
        signal,
        params: {
          org_id: orgId,
          ...(dateStr ? { target_date: dateStr } : {}),
        },
      });
      if (!Array.isArray(raw)) {
        return [];
      }
      return raw.map((appt: any): AppointmentItem => {
        if (
          appt.fee == null ||
          !appt.appointment_date ||
          !appt.appointment_time
        ) {
          throw new Error(
            "Appointment data is incomplete; refresh or contact clinic support.",
          );
        }
        const apptDate = appt.appointment_date || "";
        const apptTime = appt.appointment_time || "";
        return {
          id: appt.id,
          patient_name: appt.patient_name || "Anonymous Patient",
          patient_phone: appt.patient_phone || "",
          patient_id: appt.patient_id,
          dob: appt.dob,
          gender: appt.gender,
          blood_group: appt.blood_group,
          address: appt.address,
          reported_age: appt.reported_age,
          age_unit: appt.age_unit,
          bill_finalized_at: appt.bill_finalized_at,
          urgency_reason: appt.urgency_reason,
          doctor_name: appt.doctor_name,
          queue_state: appt.queue_state,
          appointment_date: apptDate,
          appointment_time: apptTime,
          status: (appt.status as AppointmentItem["status"]) || "scheduled",
          chief_complaint: appt.chief_complaint || "",
          source: (appt.source ||
            (appt.booked_by_type === "VOICE_AI"
              ? "ai_voice"
              : "manual")) as AppointmentItem["source"],
          payment_status: (appt.payment_status ||
            "pending") as AppointmentItem["payment_status"],
          payment_method: appt.payment_method ?? null,
          fee: Number(appt.fee),
          amount_paid: Number(appt.amount_paid || 0),
          balance_due: Number(appt.balance_due ?? appt.fee ?? 0),
          payment_receipts: appt.payment_receipts || [],
          bill_items: appt.bill_items || [],
          token_number: appt.token_number ?? null,
          display_token: appt.display_token ?? null,
          token_prefix: appt.token_prefix ?? null,
          doctor_id: appt.doctor_id ?? null,
          appointment_window_start: appt.start_time ?? null,
          appointment_window_end: appt.end_time ?? null,
          checked_in_at: appt.checked_in_at ?? null,
          consultation_started_at: appt.consultation_started_at ?? null,
          consultation_ended_at: appt.consultation_ended_at ?? null,
          actual_duration_seconds: appt.actual_duration_seconds ?? null,
        };
      });
    },
    enabled: Boolean(orgId && dateStr) && enabled,
    staleTime: 1000 * 60,
    refetchOnWindowFocus: false,
  });
}

export function useClinicAnalyticsQuery(
  orgId?: string | null,
  period: "week" | "month" | "year" = "month",
) {
  return useQuery({
    queryKey: clinicQueryKeys.analytics(orgId, period),
    queryFn: ({ signal }) =>
      httpClient.get<ClinicAnalyticsData>(
        "/api/v1/appointments/analytics/data",
        {
          orgId,
          signal,
          params: { period },
        },
      ),
    enabled: Boolean(orgId),
    staleTime: 1000 * 60,
  });
}

export function useClinicRevenueQuery(
  orgId?: string | null,
  period: "today" | "week" | "month" | "all" = "today",
) {
  return useQuery({
    queryKey: clinicQueryKeys.revenue(orgId, period),
    queryFn: ({ signal }) =>
      httpClient.get<ClinicRevenueResponse>(
        "/api/v1/appointments/revenue/data",
        {
          orgId,
          signal,
          params: { period },
        },
      ),
    enabled: Boolean(orgId),
    staleTime: 1000 * 60,
  });
}

export function useClinicPatientsQuery(
  orgId?: string | null,
  enabled = true,
  options: { page?: number; search?: string; patientId?: string | null } = {},
) {
  return useQuery({
    queryKey: [...clinicQueryKeys.patients(orgId), options],
    queryFn: ({ signal }) =>
      httpClient.get<PatientRecordItem[]>("/api/v1/appointments/patients", {
        orgId,
        signal,
        params: {
          limit: 50,
          offset: ((options.page || 1) - 1) * 50,
          search: options.search || "",
          patient_id: options.patientId,
        },
      }),
    enabled: Boolean(orgId) && enabled,
    staleTime: 60_000,
  });
}

export function useAppointmentEventsQuery(
  appointmentId?: string | null,
  orgId?: string | null,
) {
  return useQuery({
    queryKey: ["clinic", "appointment-events", orgId, appointmentId],
    queryFn: async ({ signal }): Promise<VisitEventItem[]> => {
      if (!appointmentId) return [];
      const res = await httpClient.get<VisitEventItem[]>(
        `/api/v1/appointments/${appointmentId}/events`,
        { orgId, signal },
      );
      return res || [];
    },
    enabled: Boolean(orgId && appointmentId),
    staleTime: 3000,
  });
}

export function useClinicQueueQuery(orgId?: string | null) {
  return useQuery({
    queryKey: clinicQueryKeys.queue(orgId),
    queryFn: ({ signal }) =>
      httpClient.get<AppointmentItem[]>("/api/v1/appointments/queue", {
        orgId,
        signal,
      }),
    enabled: Boolean(orgId),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
  });
}

export function useClinicCallsQuery(
  orgId: string | null,
  options: {
    page: number;
    search: string;
    targetDate: string | null;
    category: string;
  },
) {
  return useQuery({
    queryKey: [...clinicQueryKeys.calls(orgId), options],
    queryFn: ({ signal }) =>
      httpClient.get<{
        logs: ClinicCallSessionItem[];
        counts: { all: number; missed: number; ai: number; emergency: number };
        total: number;
        has_more: boolean;
      }>("/api/v1/voice/daily-call-logs", {
        orgId,
        signal,
        params: {
          limit: 50,
          offset: (options.page - 1) * 50,
          search: options.search,
          target_date: options.targetDate,
          category: options.category,
        },
      }),
    enabled: Boolean(orgId),
    staleTime: 30_000,
  });
}

export function useClinicRealTimeSync(orgId?: string | null) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!orgId) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const scheduleRefresh = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = undefined;
        for (const key of [
          "appointments",
          "queue",
          "billing",
          "arrival-options",
          "dashboard",
          "slots",
          "capacity-ledger",
          "leave-collisions",
          "patient-lookup",
        ]) {
          void queryClient.invalidateQueries(
            { queryKey: ["clinic", key, orgId], refetchType: "active" },
            { cancelRefetch: false },
          );
        }
      }, 250);
    };
    const broadcast =
      typeof BroadcastChannel !== "undefined"
        ? new BroadcastChannel("dispatch_clinic_sync")
        : null;
    if (broadcast)
      broadcast.onmessage = (event) => {
        if (event.data?.type === "SYNC" && event.data.orgId === orgId)
          scheduleRefresh();
      };
    const supabase = createClient();
    const channel = supabase
      .channel(`clinic-appointments-${orgId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "appointments",
          filter: `org_id=eq.${orgId}`,
        },
        scheduleRefresh,
      )
      .subscribe();
    return () => {
      if (timer) clearTimeout(timer);
      broadcast?.close();
      void supabase.removeChannel(channel);
    };
  }, [orgId, queryClient]);
}

export function usePatientLookup(
  orgId: string | null,
  phone: string,
  name: string,
  enabled: boolean,
) {
  const [input, setInput] = useState({ phone, name });
  useEffect(() => {
    const timer = setTimeout(() => setInput({ phone, name }), 350);
    return () => clearTimeout(timer);
  }, [phone, name]);
  const settled = input.phone === phone && input.name === name;
  const query = useQuery({
    queryKey: ["clinic", "patient-lookup", orgId, input.phone, input.name],
    queryFn: ({ signal }) =>
      httpClient.get<
        Array<{
          id: string;
          name: string;
          phone: string;
          priority_reason: string | null;
          dob?: string;
          gender?: string;
          blood_group?: string;
          address?: string;
          reported_age?: number;
          age_unit?: "years" | "months";
        }>
      >("/api/v1/appointments/patient-lookup", {
        orgId,
        signal,
        params: input,
      }),
    enabled:
      Boolean(orgId) &&
      enabled &&
      settled &&
      phone.replace(/\D/g, "").length >= 5 &&
      name.trim().length > 0,
    staleTime: 30_000,
  });
  return { ...query, data: settled && enabled ? query.data : undefined };
}

export function useLeaveCollisionQuery(
  orgId: string | null,
  startDate: string,
  endDate: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["clinic", "leave-collisions", orgId, startDate, endDate],
    queryFn: ({ signal }) =>
      httpClient.get<{ count: number }>(
        "/api/v1/appointments/leave-collisions",
        { orgId, signal, params: { start_date: startDate, end_date: endDate } },
      ),
    enabled:
      Boolean(orgId) &&
      enabled &&
      Boolean(startDate && endDate) &&
      endDate >= startDate,
    staleTime: 15_000,
  });
}

export function useClinicDoctors(orgId?: string | null) {
  return useQuery({
    queryKey: ["clinic", "doctors", orgId],
    queryFn: () =>
      httpClient.get<Array<{ id: string; name: string }>>(
        "/api/v1/appointments/doctors",
        { orgId },
      ),
    enabled: Boolean(orgId),
  });
}

export function useClinicBillingVisits(orgId?: string | null) {
  return useQuery({
    queryKey: ["clinic", "billing", orgId],
    queryFn: () =>
      httpClient.get<AppointmentItem[]>("/api/v1/appointments/billing", {
        orgId,
      }),
    enabled: Boolean(orgId),
  });
}

export function useClinicTimezone(orgId?: string | null) {
  const query = useQuery({
    queryKey: ["clinic-organization", orgId],
    queryFn: () =>
      httpClient.get<{ timezone?: string }>(`/api/v1/org/${orgId}`, { orgId }),
    enabled: Boolean(orgId),
    staleTime: 300000,
  });
  return query.data?.timezone || "";
}

export function useArrivalOptions(
  orgId: string | null,
  date: string,
  doctorId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["clinic", "arrival-options", orgId, date, doctorId],
    queryFn: () =>
      httpClient.get<{ available_slots: string[]; reason?: string }>(
        "/api/v1/appointments/arrival-options",
        { orgId, params: { target_date: date, doctor_id: doctorId } },
      ),
    enabled: Boolean(orgId && date && doctorId && enabled),
  });
}

export interface VoiceAllowanceData {
  limit_seconds: number;
  used_seconds: number;
  reserved_seconds: number;
  remaining_seconds: number;
  max_call_seconds: number;
}

export function useVoiceAllowanceQuery(orgId?: string | null) {
  return useQuery({
    queryKey: ["clinic", "voice-allowance", orgId],
    queryFn: () =>
      httpClient.get<VoiceAllowanceData>("/api/v1/calls/allowance", {
        orgId,
      }),
    enabled: Boolean(orgId),
    refetchInterval: 30000,
    staleTime: 15000,
  });
}
