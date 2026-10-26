import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  EmergencyBlock,
  DoctorLeave,
  DateOverride,
  RescheduleAuditItem,
  Escalation,
  PatientRecordItem,
} from "./types";

interface ClinicStoreState {
  followUpVisit: {id: string; patient_id?: string; patient_name: string; patient_phone: string; doctor_id?: string | null} | null;
  setFollowUpVisit: (visit: ClinicStoreState['followUpVisit']) => void;
  orgId: string | null;
  doctorId: string | null;
  setTenantSession: (orgId: string, doctorId?: string) => void;

  activeRole: "doctor" | "receptionist";
  setActiveRole: (role: "doctor" | "receptionist") => void;

  isDayBlocked: boolean;
  isBookingModalOpen: boolean;
  bookingModalType: "Walk-in" | "Pre-booked";
  bookingInitialDate: string | null;
  bookingInitialTime: string | null;
  leaves: DoctorLeave[];
  dateOverrides: DateOverride[];
  emergencyBlocks: EmergencyBlock[];
  rescheduleAudits: RescheduleAuditItem[];
  actionCenterItems: Escalation[];
  patients: PatientRecordItem[];
  missedCallsCount: number;
  setMissedCallsCount: (count: number) => void;
  lastViewedCallsTimestamp: number | null;
  viewedCallsByOrg: Record<string, number>;
  markCallsAsViewed: () => void;

  activeSettingsTab:
    | "doctor-profile"
    | "ai-voice"
    | "opd-schedule"
    | "staff-access"
    | "billing-catalog";
  setActiveSettingsTab: (
    tab:
      | "doctor-profile"
      | "ai-voice"
      | "opd-schedule"
      | "staff-access"
      | "billing-catalog",
  ) => void;
  setBookingModalOpen: (open: boolean) => void;
  setBookingModalType: (type: "Walk-in" | "Pre-booked") => void;
  setBookingInitialSlot: (date: string | null, time: string | null) => void;
  toggleDayEmergencyBlock: () => void;
  setDayEmergencyBlock: (blocked: boolean) => void;
  triggerEmergencyBlock: (
    scope: "full_day" | "remainder_of_day",
    reason: string,
    blockedFromTime?: string,
  ) => void;
  clearEmergencyBlock: (id: string) => void;
  addLeave: (leave: Omit<DoctorLeave, "id" | "createdAt">) => void;
  removeLeave: (id: string) => void;
  addDateOverride: (override: Omit<DateOverride, "id">) => void;
  removeDateOverride: (id: string) => void;
  transferAppointment: (
    id: string,
    newDate: string,
    newTime: string,
    reason?: string,
  ) => void;
  resolveActionCenterItem: (id: string) => void;
  savePatientNote: (id: string, note: string) => void;
}

export const useClinicStore = create<ClinicStoreState>()(
  persist(
    (set) => ({
      followUpVisit: null,
      setFollowUpVisit: (visit) => set({followUpVisit: visit}),
      orgId: null,
      doctorId: null,
      activeRole: "doctor",
      setActiveRole: (role) => set({ activeRole: role }),
      activeSettingsTab: "doctor-profile",
      setActiveSettingsTab: (tab) => set({ activeSettingsTab: tab }),
      setTenantSession: (orgId: string, doctorId?: string) =>
        set((state) => ({ orgId, doctorId: doctorId || null,
          missedCallsCount: state.orgId === orgId ? state.missedCallsCount : 0,
          lastViewedCallsTimestamp: state.viewedCallsByOrg[orgId] ?? null })),

      isDayBlocked: false,
      isBookingModalOpen: false,
      bookingModalType: "Pre-booked",
      bookingInitialDate: null,
      bookingInitialTime: null,
      leaves: [],
      dateOverrides: [],
      emergencyBlocks: [],
      rescheduleAudits: [],
      actionCenterItems: [],
      patients: [],
      missedCallsCount: 0,
      lastViewedCallsTimestamp: null,
      viewedCallsByOrg: {},
      setMissedCallsCount: (count) => set({ missedCallsCount: count }),
      setBookingModalOpen: (open) => set(state => ({ isBookingModalOpen: open, followUpVisit: open ? state.followUpVisit : null, bookingInitialDate: open ? state.bookingInitialDate : null, bookingInitialTime: open ? state.bookingInitialTime : null })),
      markCallsAsViewed: () => set((state) => {
        if (!state.orgId) return {};
        const timestamp = Date.now();
        return { missedCallsCount: 0, lastViewedCallsTimestamp: timestamp,
          viewedCallsByOrg: { ...state.viewedCallsByOrg, [state.orgId]: timestamp } };
      }),
      setBookingModalType: (type) => set({ bookingModalType: type }),
      setBookingInitialSlot: (date, time) =>
        set({ bookingInitialDate: date, bookingInitialTime: time }),

      toggleDayEmergencyBlock: () =>
        set((state) => ({ isDayBlocked: !state.isDayBlocked })),

      setDayEmergencyBlock: (blocked) => set({ isDayBlocked: blocked }),

      triggerEmergencyBlock: (scope, reason, blockedFromTime) =>
        set((state) => {
          const todayISO = new Date().toISOString().split("T")[0];
          const newBlock: EmergencyBlock = {
            id: `block-${Date.now()}`,
            date: todayISO,
            scope,
            blockedFromTime,
            reason,
            createdAt: new Date().toISOString(),
          };
          return {
            isDayBlocked: true,
            emergencyBlocks: [newBlock, ...state.emergencyBlocks],
          };
        }),

      clearEmergencyBlock: (id) =>
        set((state) => ({
          emergencyBlocks: state.emergencyBlocks.filter((b) => b.id !== id),
          isDayBlocked:
            state.emergencyBlocks.filter((b) => b.id !== id).length > 0,
        })),

      addLeave: (leave) =>
        set((state) => ({
          leaves: [
            {
              ...leave,
              id: `leave-${Date.now()}`,
              createdAt: new Date().toISOString(),
            },
            ...state.leaves,
          ],
        })),

      removeLeave: (id) =>
        set((state) => ({
          leaves: state.leaves.filter((l) => l.id !== id),
        })),

      addDateOverride: (override) =>
        set((state) => ({
          dateOverrides: [
            {
              ...override,
              id: `ovr-${Date.now()}`,
            },
            ...state.dateOverrides,
          ],
        })),

      removeDateOverride: (id) =>
        set((state) => ({
          dateOverrides: state.dateOverrides.filter((o) => o.id !== id),
        })),

      transferAppointment: (
        id,
        newDate,
        newTime,
        reason = "manual_doctor_transfer",
      ) =>
        set((state) => {
          const audit: RescheduleAuditItem = {
            id: `audit-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
            appointmentId: id,
            patientName: "Transferred Patient",
            patientPhone: "",
            originalDate: "Today",
            originalSlot: "",
            newDate,
            newSlot: newTime,
            triggerReason:
              (reason as RescheduleAuditItem["triggerReason"]) ||
              "manual_doctor_transfer",
            notificationStatus: "sent",
            createdAt: new Date().toISOString(),
          };

          return {
            rescheduleAudits: [audit, ...state.rescheduleAudits],
          };
        }),

      resolveActionCenterItem: (id) =>
        set((state) => ({
          actionCenterItems: state.actionCenterItems.map((it) =>
            it.id === id ? { ...it, status: "resolved" } : it,
          ),
        })),

      savePatientNote: (id, note) =>
        set((state) => ({
          patients: state.patients.map((p) =>
            p.id === id ? { ...p, notes: [note, ...(p.notes || [])] } : p,
          ),
        })),
    }),
    {
      name: "clinic-store-storage",
    },
  ),
);
