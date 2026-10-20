import { useClinicStore } from "../store";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { httpClient } from "@/lib/api/httpClient";
import { clinicQueryKeys } from "./useClinicQueries";
import { AppointmentItem, ClinicRevenueResponse, ClinicLiveDashboardData, BillItem } from "../types";

export interface WalkInPayload {
  gender?: string;
  blood_group?: string;
  address?: string;
  reported_age?: number;
  age_unit?: "years" | "months";
  dob?: string;
  patient_id?: string;
  doctor_id?: string;
  patient_name: string;
  patient_phone: string;
  appointment_date: string;
  chief_complaint?: string;
  fee?: number;
  is_walkin: boolean;
  appointment_time?: string;
  is_arrived?: boolean;
  payment_status?: string;
  payment_method?: string;
  token_prefix?: string;
}

export interface ScheduledBookingPayload {
  dob?: string;
  reported_age?: number;
  age_unit?: "years" | "months";
  patient_id?: string;
  doctor_id?: string;
  previous_visit_id?: string;
  patient_name: string;
  patient_phone: string;
  appointment_date: string;
  appointment_time: string;
  chief_complaint?: string;
  fee?: number;
}

export interface UpdateStatusPayload {
  appointmentId: string;
  status: AppointmentItem["status"];
}

export interface CollectFeePayload {
  idempotencyKey?: string;
  adjustmentReason?: string;
  appointmentId: string;
  paymentMethod?: "UPI" | "Cash" | string;
  paymentStatus?: "paid" | "pending";
  fee?: number;
  billItems?: BillItem[];
  amountReceived?: number;
  reference?: string;
}

export interface DoctorNotesPayload {
  appointmentId: string;
  doctorNotes: string;
  recentDiagnosis?: string;
  billItems?: BillItem[];
  fee?: number;
}

export function notifyClinicSync() {
  const orgId = useClinicStore.getState().orgId;
  if (typeof window !== "undefined" && "BroadcastChannel" in window) {
    try {
      const channel = new BroadcastChannel("dispatch_clinic_sync");
      channel.postMessage({ type: "SYNC", orgId, timestamp: Date.now() });
      channel.close();
    } catch {}
  }
}

export function useAddWalkInMutation(orgId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WalkInPayload) =>
      httpClient.post("/api/v1/appointments/walkin", payload, { orgId }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.dashboard(orgId),
      });
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.slots(orgId, variables.appointment_date),
      });
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.appointments(orgId),
      });
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.revenue(orgId),
      });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}
export function useBookAppointmentMutation(orgId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ScheduledBookingPayload) =>
      httpClient.post('/api/v1/appointments/book', payload, { orgId }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.slots(orgId, variables.appointment_date) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "arrival-options", orgId] });
      queryClient.invalidateQueries({ queryKey: ["clinic", "patient-lookup", orgId] });
      notifyClinicSync();
    },
  });
}

export function useUpdateAppointmentStatusMutation(orgId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ appointmentId, status }: UpdateStatusPayload) =>
      httpClient.patch(
        `/api/v1/appointments/${appointmentId}/status`,
        { status },
        { orgId },
      ),
    onMutate: async ({ appointmentId, status }: UpdateStatusPayload) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId ? { ...item, status } : item
          )
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId ? { ...item, status } : item
          )
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            const updatedWaiting = old.waiting_queue.map((item) =>
              item.appointment_id === appointmentId ? { ...item, status } : item
            );
            let updatedActive = old.active_patient;
            if (status === 'in_progress') {
              const match = old.waiting_queue.find((item) => item.appointment_id === appointmentId);
              if (match) {
                updatedActive = { ...match, status: 'in_progress' };
              }
            } else if (status === 'completed' || status === 'cancelled') {
              if (old.active_patient?.appointment_id === appointmentId) {
                updatedActive = null;
              }
            }
            return {
              ...old,
              active_patient: updatedActive,
              waiting_queue: updatedWaiting,
            };
          }
        );
      }

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _vars, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useLateArrivalMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/late-arrival`, {}, { orgId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.slots(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
    },
  });
}

export interface EndOfDayAction {
  appointment_id: string;
  action: 'rollover' | 'convert' | 'cancel';
  target_date?: string;
  target_time?: string;
}

export function useEndOfDayActionMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EndOfDayAction) =>
      httpClient.post('/api/v1/appointments/end-of-day-action', payload, { orgId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.slots(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.revenue(orgId) });
    },
  });
}

export function useRolloverQueueMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      httpClient.post('/api/v1/appointments/rollover-queue', {}, { orgId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.slots(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.revenue(orgId) });
    },
  });
}

export interface BatchReconciliationItem {
  appointment_id: string;
  action: 'rollover_morning' | 'rollover_same_time' | 'custom_time' | 'cancel';
  target_date?: string;
  target_time?: string;
  patient_confirmed?: boolean;
}

export interface BatchReconciliationPayload {
  actions: BatchReconciliationItem[];
}

export function useBatchReconcileQueueMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BatchReconciliationPayload) =>
      httpClient.post('/api/v1/appointments/batch-reconciliation', payload, { orgId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.slots(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.revenue(orgId) });
    },
  });
}


export function useCollectClinicFeeMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({appointmentId, paymentMethod, paymentStatus, fee, billItems, amountReceived, reference, idempotencyKey, adjustmentReason}: CollectFeePayload) =>
      httpClient.patch(`/api/v1/appointments/${appointmentId}/collect-fee`, {
        payment_method: paymentMethod, payment_status: paymentStatus, fee, bill_items: billItems,
        amount_received: amountReceived, reference, idempotency_key: idempotencyKey || crypto.randomUUID(), adjustment_reason: adjustmentReason,
      }, {orgId}),
    onSettled: () => {
      queryClient.invalidateQueries({queryKey: ['clinic']});
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useSaveDoctorNotesMutation(orgId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      appointmentId,
      doctorNotes,
      recentDiagnosis,
      billItems,
      fee,
    }: DoctorNotesPayload) =>
      httpClient.patch(
        `/api/v1/appointments/${appointmentId}/notes`,
        {
          doctor_notes: doctorNotes,
          recent_diagnosis: recentDiagnosis,
          bill_items: billItems,
          fee,
        },
        { orgId },
      ),
    onMutate: async ({ appointmentId, doctorNotes, recentDiagnosis, billItems, fee }) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? {
                  ...item,
                  doctor_notes: doctorNotes,
                  recent_diagnosis: recentDiagnosis || item.recent_diagnosis,
                  bill_items: billItems !== undefined ? billItems : item.bill_items,
                  fee: fee !== undefined ? fee : item.fee,
                }
              : item
          )
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            return {
              ...old,
              active_patient:
                old.active_patient?.appointment_id === appointmentId
                  ? {
                      ...old.active_patient,
                      doctor_notes: doctorNotes,
                    }
                  : old.active_patient,
            };
          }
        );
      }

      return { prevAppointments, prevDashboard };
    },
    onError: (_err, _vars, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useSavePatientEhrNoteMutation(orgId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ patientId, note }: { patientId: string; note: string }) =>
      httpClient.post(
        `/api/v1/appointments/patients/${patientId}/notes`,
        { note },
        { orgId },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.patients(orgId),
      });
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.dashboard(orgId),
      });
    },
  });
}

export function useResolveEmergencyCallbackMutation(orgId?: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sessionId: string) =>
      httpClient.post(
        `/api/v1/appointments/emergency-callbacks/${sessionId}/resolve`,
        {},
        { orgId },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: clinicQueryKeys.dashboard(orgId),
      });
    },
  });
}

export function useArriveAppointmentMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (param: string | { appointmentId: string; data?: { doctor_id?: string; patient_phone?: string; reported_age?: number; age_unit?: "years" | "months"; patient_name?: string; dob?: string; gender?: string; blood_group?: string; address?: string; chief_complaint?: string; payment_status?: string; payment_method?: string; fee?: number; bill_items?: BillItem[] } }) => {
      const appointmentId = typeof param === 'string' ? param : param.appointmentId;
      const body = typeof param === 'object' && param.data ? param.data : {};
      return httpClient.post(`/api/v1/appointments/${appointmentId}/arrive`, body, { orgId });
    },
    onMutate: async (param) => {
      const appointmentId = typeof param === 'string' ? param : param.appointmentId;
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? {
                  ...item,
                  status: 'arrived' as const,
                  patient_name:
                    typeof param === 'object' && param.data?.patient_name
                      ? param.data.patient_name
                      : item.patient_name,
                  checked_in_at: item.checked_in_at || new Date().toISOString(),
                  payment_status:
                    typeof param === 'object' && param.data?.payment_status
                      ? (param.data.payment_status as any)
                      : item.payment_status,
                  payment_method:
                    typeof param === 'object' && param.data?.payment_method
                      ? param.data.payment_method
                      : item.payment_method,
                  fee:
                    typeof param === 'object' && param.data?.fee !== undefined
                      ? param.data.fee
                      : item.fee,
                  bill_items:
                    typeof param === 'object' && param.data?.bill_items !== undefined
                      ? param.data.bill_items
                      : item.bill_items,
                  chief_complaint:
                    typeof param === 'object' && param.data?.chief_complaint
                      ? param.data.chief_complaint
                      : item.chief_complaint,
                }
              : item
          )
      );

      return { prevAppointments };
    },
    onError: (_err, _param, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.revenue(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useCallPatientMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/call`, {}, { orgId }),
    onMutate: async (appointmentId: string) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'in_progress' as const }
              : item.status === 'in_progress'
                ? { ...item, status: 'arrived' as const }
                : item
          )
      );

      return { prevAppointments };
    },
    onError: (_err, _appointmentId, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useStartConsultationMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/start-consultation`, {}, { orgId }),
    onMutate: async (appointmentId: string) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'in_progress' as const }
              : item.status === 'in_progress'
                ? { ...item, status: 'arrived' as const }
                : item
          )
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'in_progress' as const }
              : item.status === 'in_progress'
                ? { ...item, status: 'arrived' as const }
                : item
          )
      );

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _appointmentId, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useCompleteConsultationMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/complete`, {}, { orgId }),
    onMutate: async (appointmentId: string) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'completed' as const }
              : item
          )
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'completed' as const }
              : item
          )
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            return {
              ...old,
              active_patient: old.active_patient?.appointment_id === appointmentId ? null : old.active_patient,
            };
          }
        );
      }

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _appointmentId, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.revenue(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useSkipPatientMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/skip`, {}, { orgId }),
    onMutate: async (appointmentId: string) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      let targetItem: AppointmentItem | undefined;

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) => {
            if (item.id === appointmentId) {
              targetItem = { ...item, status: 'skipped' as const };
              return targetItem;
            }
            return item;
          })
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) => {
          const exists = old.some((item) => item.id === appointmentId);
          if (exists) {
            return old.map((item) =>
              item.id === appointmentId
                ? { ...item, status: 'skipped' as const }
                : item
            );
          }
          if (targetItem) {
            return [...old, targetItem];
          }
          const fromAppointments = prevAppointments?.find((item) => item.id === appointmentId);
          if (fromAppointments) {
            return [...old, { ...fromAppointments, status: 'skipped' as const }];
          }
          return old;
        }
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            return {
              ...old,
              active_patient: old.active_patient?.appointment_id === appointmentId ? null : old.active_patient,
              waiting_queue: old.waiting_queue.map((item) =>
                item.appointment_id === appointmentId
                  ? { ...item, status: 'skipped' as const }
                  : item
              ),
            };
          }
        );
      }

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _appointmentId, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useMoveTomorrowMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/move-tomorrow`, {}, { orgId }),
    onMutate: async (appointmentId: string) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) => old.filter((item) => item.id !== appointmentId)
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) => old.filter((item) => item.id !== appointmentId)
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            return {
              ...old,
              active_patient: old.active_patient?.appointment_id === appointmentId ? null : old.active_patient,
              waiting_queue: old.waiting_queue.filter((item) => item.appointment_id !== appointmentId),
            };
          }
        );
      }

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _vars, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useReinsertPatientMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: string) =>
      httpClient.post(`/api/v1/appointments/${appointmentId}/reinsert`, {}, { orgId }),
    onMutate: async (appointmentId: string) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'arrived' as const }
              : item
          )
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId
              ? { ...item, status: 'arrived' as const }
              : item
          )
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            return {
              ...old,
              waiting_queue: old.waiting_queue.map((item) =>
                item.appointment_id === appointmentId
                  ? { ...item, status: 'arrived' as const }
                  : item
              ),
            };
          }
        );
      }

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _appointmentId, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export interface ReschedulePayload {
  appointmentId: string;
  new_date: string;
  new_time: string;
  reason?: string;
}

export function useRescheduleAppointmentMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, new_date, new_time, reason }: ReschedulePayload) =>
      httpClient.patch(
        `/api/v1/appointments/${appointmentId}/reschedule`,
        { new_date, new_time, reason },
        { orgId },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.slots(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}

export function useCancelAppointmentMutation(orgId?: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, reason }: { appointmentId: string; reason?: string }) =>
      httpClient.post(
        `/api/v1/appointments/${appointmentId}/cancel`,
        { reason },
        { orgId },
      ),
    onMutate: async ({ appointmentId }) => {
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      await queryClient.cancelQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });

      const prevAppointments = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.appointments(orgId));
      const prevQueue = queryClient.getQueryData<AppointmentItem[]>(clinicQueryKeys.queue(orgId));
      const prevDashboard = queryClient.getQueryData<ClinicLiveDashboardData>(clinicQueryKeys.dashboard(orgId));

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.appointments(orgId),
        (old = []) =>
          old.map((item) =>
            item.id === appointmentId ? { ...item, status: 'cancelled' as const } : item
          )
      );

      queryClient.setQueryData<AppointmentItem[]>(
        clinicQueryKeys.queue(orgId),
        (old = []) => old.filter((item) => item.id !== appointmentId)
      );

      if (prevDashboard) {
        queryClient.setQueryData<ClinicLiveDashboardData>(
          clinicQueryKeys.dashboard(orgId),
          (old) => {
            if (!old) return old;
            return {
              ...old,
              active_patient: old.active_patient?.appointment_id === appointmentId ? null : old.active_patient,
              waiting_queue: old.waiting_queue.filter((item) => item.appointment_id !== appointmentId),
            };
          }
        );
      }

      return { prevAppointments, prevQueue, prevDashboard };
    },
    onError: (_err, _vars, context) => {
      if (context?.prevAppointments) {
        queryClient.setQueryData(clinicQueryKeys.appointments(orgId), context.prevAppointments);
      }
      if (context?.prevQueue) {
        queryClient.setQueryData(clinicQueryKeys.queue(orgId), context.prevQueue);
      }
      if (context?.prevDashboard) {
        queryClient.setQueryData(clinicQueryKeys.dashboard(orgId), context.prevDashboard);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.dashboard(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.appointments(orgId) });
      queryClient.invalidateQueries({ queryKey: ["clinic", "billing", orgId] });
      queryClient.invalidateQueries({ queryKey: clinicQueryKeys.queue(orgId) });
      notifyClinicSync();
    },
  });
}
