'use client';

import {httpClient} from '@/lib/api/httpClient';
import {useQueryClient} from '@tanstack/react-query';
import React, { useMemo, useState, useEffect } from 'react';
import { useClinicStore } from '../store';
import { AppointmentItem, BillItem } from '../types';
import {
  useClinicAppointmentsQuery,
  useClinicSlotsQuery,
  useClinicQueueQuery,
  useClinicDoctors,
  useClinicBillingVisits,
  useClinicTimezone,
} from '../_hooks/useClinicQueries';
import {
  useStartConsultationMutation,
  useCompleteConsultationMutation,
  useArriveAppointmentMutation,
  useSkipPatientMutation,
  useReinsertPatientMutation,
  useCancelAppointmentMutation,
  useCollectClinicFeeMutation,
} from '../_hooks/useClinicMutations';
import { ScheduleHeader } from './_components/ScheduleHeader';
import { ChamberBanner } from './_components/ChamberBanner';
import { QueueTable } from './_components/QueueTable';
import { ArrivalWindowsSidebar } from './_components/ArrivalWindowsSidebar';
import { RescheduleModal } from './_components/RescheduleModal';
import { EndOfDayModal } from './_components/EndOfDayModal';
import QuickBillModal from '../_components/QuickBillModal';
import PatientCheckInModal from './_components/PatientCheckInModal';
import { UrgentPatientModal } from './_components/UrgentPatientModal';
import { ActionConfirmModal } from '../_components/ActionConfirmModal';
import { useRouter } from 'next/navigation';
import { CheckCircle2, RotateCcw, X } from 'lucide-react';
import { parseTimeToMinutes } from './_utils/timeUtils';
import { formatDateISO } from '../utils';

function clinicToday(timezone: string): string {
  return timezone
    ? new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
    : '';
}

export default function ClinicSchedulePage() {
  const orgId = useClinicStore((s) => s.orgId);
  const setBookingModalOpen = useClinicStore((s) => s.setBookingModalOpen);
  const setBookingModalType = useClinicStore((s) => s.setBookingModalType);
  const setBookingInitialSlot = useClinicStore((s) => s.setBookingInitialSlot);

  const {data: doctors = []} = useClinicDoctors(orgId);
  const {data: billingVisits = []} = useClinicBillingVisits(orgId);
  const timezone = useClinicTimezone(orgId);
  const clinicDoctorId = doctors[0]?.id || '';
  const [billingFilter, setBillingFilter] = useState<'ready' | 'outstanding' | 'settled'>('ready');
  const queryClient = useQueryClient();
  const [isUrgencyOpen, setIsUrgencyOpen] = useState(false);
  const [isUrgencySubmitting, setIsUrgencySubmitting] = useState(false);
  const [billTarget, setBillTarget] = useState<AppointmentItem | null>(null);
  const activeRole = useClinicStore((s) => s.activeRole);

  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(() => clinicToday(timezone));
  const [isEndOfDayModalOpen, setIsEndOfDayModalOpen] = useState(false);
  const router = useRouter();
  const [rescheduleTarget, setRescheduleTarget] = useState<AppointmentItem | null>(null);
  const [isRescheduleModalOpen, setIsRescheduleModalOpen] = useState(false);
  const [checkInAppointment, setCheckInAppointment] = useState<AppointmentItem | null>(null);
  const [activeTab, setActiveTab] = useState<'queue' | 'due' | 'completed' | 'all'>(() =>
    activeRole === 'doctor' ? 'queue' : 'queue'
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [collectingFeeId, setCollectingFeeId] = useState<string | null>(null);
  const [actionState, setActionState] = useState<{ id: string; action: 'arrive' | 'call' | 'complete' | 'skip' | 'reinsert' | 'move_tomorrow' } | null>(null);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const [confirmModal, setConfirmModal] = useState<{
    type: 'complete' | 'cancel';
    appointmentId: string;
    patientName: string;
  } | null>(null);
  const [undoToast, setUndoToast] = useState<{
    appointmentId: string;
    patientName: string;
  } | null>(null);

  useEffect(() => {
    if (activeRole === 'doctor' && activeTab === 'due') {
      setActiveTab('queue');
    }
  }, [activeRole, activeTab]);

  useEffect(() => {
    if (timezone && !selectedDate) setSelectedDate(clinicToday(timezone));
  }, [timezone, selectedDate]);

  const isToday = useMemo(() => Boolean(selectedDate && selectedDate === clinicToday(timezone)), [selectedDate, timezone]);

  const dateLabel = useMemo(() => {
    if (!selectedDate || !timezone) return 'Clinic timezone unavailable';
    const todayStr = clinicToday(timezone);
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = formatDateISO(tomorrow);
    const targetDate = new Date(selectedDate + 'T00:00:00');

    if (selectedDate === todayStr) return `Today, ${targetDate.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}`;
    if (selectedDate === tomorrowStr) return `Tomorrow, ${targetDate.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}`;
    return targetDate.toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' });
  }, [selectedDate, timezone]);

  const handlePrevDay = () => {
    const d = new Date(selectedDate + 'T00:00:00');
    d.setDate(d.getDate() - 1);
    const nextStr = formatDateISO(d);
    setSelectedDate(nextStr);
    if (nextStr !== clinicToday(timezone)) {
      setActiveTab('queue');
    } else {
      setActiveTab('queue');
    }
  };

  const handleNextDay = () => {
    const d = new Date(selectedDate + 'T00:00:00');
    d.setDate(d.getDate() + 1);
    const nextStr = formatDateISO(d);
    setSelectedDate(nextStr);
    if (nextStr !== clinicToday(timezone)) {
      setActiveTab('queue');
    } else {
      setActiveTab('queue');
    }
  };

  const {
    data: appointments = [],
    isLoading: isAppointmentsLoading,
  } = useClinicAppointmentsQuery(orgId, selectedDate);
  const { data: queueAppointments = [] } = useClinicQueueQuery(orgId);
  const {
    data: clinicSlotsData,
    isLoading: isSlotsLoading,
  } = useClinicSlotsQuery(orgId, selectedDate, clinicDoctorId);
  const clinicSlots = clinicSlotsData?.slots || [];

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  const startConsultationMutation = useStartConsultationMutation(orgId);
  const completeConsultationMutation = useCompleteConsultationMutation(orgId);
  const arriveMutation = useArriveAppointmentMutation(orgId);
  const skipMutation = useSkipPatientMutation(orgId);
  const reinsertMutation = useReinsertPatientMutation(orgId);
  const cancelMutation = useCancelAppointmentMutation(orgId);
  const collectFeeMutation = useCollectClinicFeeMutation(orgId);

  const dateAppointments = useMemo(() => {
    return appointments.filter((a) => {
      if (clinicDoctorId && a.doctor_id && a.doctor_id !== clinicDoctorId) return false;
      if (isToday && !a.appointment_date) return true;
      return a.appointment_date === selectedDate;
    });
  }, [appointments, isToday, selectedDate, clinicDoctorId]);

  const activeQueueList = useMemo(() => {
    if (!isToday) return [];
    return queueAppointments.filter(a => !clinicDoctorId || a.doctor_id === clinicDoctorId);
  }, [isToday, queueAppointments, clinicDoctorId]);

  const currentInChamber = useMemo(() => {
    return dateAppointments.find((a) => a.status === 'in_progress');
  }, [dateAppointments]);

  const nextUpPatient = useMemo(() => {
    return activeQueueList.find((a) => a.status === 'arrived');
  }, [activeQueueList]);

  const queueCount = useMemo(() => {
    if (isToday) return activeQueueList.length;
    return dateAppointments.filter((a) => ['arrived', 'in_progress', 'skipped'].includes(a.status)).length;
  }, [isToday, activeQueueList, dateAppointments]);

  const inChamberCount = useMemo(() => {
    return dateAppointments.filter((a) => a.status === 'in_progress').length;
  }, [dateAppointments]);

  const waitingOnlyCount = useMemo(() => {
    if (isToday) return activeQueueList.filter((a) => a.status === 'arrived').length;
    return dateAppointments.filter((a) => a.status === 'arrived').length;
  }, [isToday, activeQueueList, dateAppointments]);

  const expectedCount = useMemo(() => {
    return dateAppointments.filter((a) => a.status === 'scheduled').length;
  }, [dateAppointments]);

  const completedCount = useMemo(() => {
    return dateAppointments.filter((a) => a.status === 'completed').length;
  }, [dateAppointments]);

  const expectedAppointments = useMemo(() => {
    return dateAppointments
      .filter((a) => a.status === 'scheduled')
      .sort((a, b) => {
        const minA = parseTimeToMinutes(a.appointment_time) ?? 9999;
        const minB = parseTimeToMinutes(b.appointment_time) ?? 9999;
        return minA - minB;
      });
  }, [dateAppointments]);

  const completedAppointments = useMemo(() => {
    return dateAppointments
      .filter((a) => ['completed', 'cancelled'].includes(a.status))
      .sort((a, b) => {
        const tA = a.consultation_ended_at ? new Date(a.consultation_ended_at).getTime() : 0;
        const tB = b.consultation_ended_at ? new Date(b.consultation_ended_at).getTime() : 0;
        return tB - tA;
      });
  }, [dateAppointments]);

  const paymentDueAppointments = useMemo(() => billingVisits.filter(a =>
    (!clinicDoctorId || a.doctor_id === clinicDoctorId) &&
    (billingFilter === 'ready' ? !a.bill_finalized_at : billingFilter === 'outstanding' ? Boolean(a.bill_finalized_at) && (a.balance_due ?? 0) > 0 : Boolean(a.bill_finalized_at) && (a.balance_due ?? 0) === 0)
  ), [billingVisits, clinicDoctorId, billingFilter]);

  const tabAppointments = useMemo(() => {
    if (activeTab === 'queue') {
      return activeQueueList;
    }
    if (activeTab === 'due') return paymentDueAppointments;
    if (activeTab === 'completed') {
      return completedAppointments;
    }
    return [...dateAppointments].sort((a, b) => {
      const minA = parseTimeToMinutes(a.appointment_time) ?? 9999;
      const minB = parseTimeToMinutes(b.appointment_time) ?? 9999;
      if (minA !== minB) return minA - minB;
      return (a.token_number || 0) - (b.token_number || 0);
    });
  }, [activeTab, activeQueueList, paymentDueAppointments, completedAppointments, dateAppointments]);

  const filteredAppointments = useMemo(() => {
    if (!searchQuery.trim()) return tabAppointments;
    const q = searchQuery.toLowerCase().trim();
    return tabAppointments.filter((item) => {
      return (
        item.patient_name.toLowerCase().includes(q) ||
        item.patient_phone.includes(q) ||
        (item.display_token || '').toLowerCase().includes(q) ||
        (item.appointment_time || '').toLowerCase().includes(q) ||
        (item.chief_complaint || '').toLowerCase().includes(q)
      );
    });
  }, [tabAppointments, searchQuery]);

  const rolloverPatients = useMemo(() => {
    return dateAppointments.filter((a) => a.token_prefix === 'R');
  }, [dateAppointments]);

  const handleOpenReschedule = (appointment: AppointmentItem) => {
    setRescheduleTarget(appointment);
    setIsRescheduleModalOpen(true);
    setActiveMenuId(null);
  };

  const handleBookReportReview = (visit: AppointmentItem) => {
    useClinicStore.getState().setFollowUpVisit(visit);
    setBookingModalType('Pre-booked');
    setBookingInitialSlot(null, null);
    setBookingModalOpen(true);
    setActiveMenuId(null);
  };

  const handleCollectFee = (payload: {
    appointmentId: string;
    paymentMethod?: 'Cash' | 'UPI';
    paymentStatus?: 'paid' | 'pending';
    fee?: number;
    billItems?: BillItem[];
    amountReceived?: number;
    reference?: string;
    idempotencyKey?: string;
    adjustmentReason?: string;
  }) => {
    return collectFeeMutation.mutateAsync(payload, {
      onSuccess: () => setCollectingFeeId(null),
    });
  };

  const handleRequestComplete = (id: string) => {
    const appt = dateAppointments.find((a) => a.id === id);
    setConfirmModal({
      type: 'complete',
      appointmentId: id,
      patientName: appt?.patient_name || 'this patient',
    });
  };

  const handleRequestCancel = (id: string) => {
    const appt = dateAppointments.find((a) => a.id === id);
    setConfirmModal({
      type: 'cancel',
      appointmentId: id,
      patientName: appt?.patient_name || 'this patient',
    });
    setActiveMenuId(null);
  };

  const handleExecuteConfirmAction = async () => {
    if (!confirmModal) return;
    const { type, appointmentId, patientName } = confirmModal;
    if (type === 'complete') {
      setActionState({ id: appointmentId, action: 'complete' });
      try {
        const completed = await completeConsultationMutation.mutateAsync(appointmentId);
        setActiveTab("due"); setBillingFilter("ready");
        const visit = dateAppointments.find(a => a.id === appointmentId);
        if (visit) setBillTarget({...visit, status: "completed"});
        setUndoToast({ appointmentId, patientName });
      } finally {
        setActionState(null);
        setConfirmModal(null);
      }
    } else if (type === 'cancel') {
      try {
        await cancelMutation.mutateAsync({ appointmentId });
      } finally {
        setConfirmModal(null);
      }
    }
  };

  const handleUndoCompletion = async () => {
    if (!undoToast) return;
    try {
      await reinsertMutation.mutateAsync(undoToast.appointmentId);
      setUndoToast(null);
    } catch { }
  };

  return (
    <div className="w-full space-y-4 pb-12">
      <ScheduleHeader
        isToday={isToday}
        waitingOnlyCount={waitingOnlyCount}
        inChamberCount={inChamberCount}
        expectedCount={expectedCount}
        dateAppointmentsCount={dateAppointments.length}
        selectedDate={selectedDate}
        dateLabel={dateLabel}
        isCalendarOpen={isCalendarOpen}
        setIsCalendarOpen={setIsCalendarOpen}
        onPrevDay={handlePrevDay}
        onNextDay={handleNextDay}
        onSelectDate={(d) => {
          setSelectedDate(d);
          if (d !== clinicToday(timezone)) {
            setActiveTab('queue');
          } else {
            setActiveTab('queue');
          }
        }}
        onSelectToday={() => {
          setSelectedDate(clinicToday(timezone));
          setActiveTab('queue');
        }}
        onOpenEndOfDay={() => setIsEndOfDayModalOpen(true)}
        onManageOverrides={() => router.push(`/clinic/schedule/history?type=all&date=${selectedDate}`)}
        onOpenUrgency={() => setIsUrgencyOpen(true)}
        rolloverCount={rolloverPatients.length}
      />


      {activeTab === 'due' && (
        <div className="flex flex-wrap items-end gap-2.5 rounded-2xl border border-[#EAE6DF] bg-[#FBF9F5] px-4 py-3 shadow-2xs">
          <label className="flex min-w-0 flex-col gap-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
            Billing view
            <select aria-label="Billing status" value={billingFilter} onChange={event => setBillingFilter(event.target.value as typeof billingFilter)} className="h-9 min-w-[190px] rounded-xl border border-neutral-200 bg-white px-3 text-xs font-semibold normal-case tracking-normal text-neutral-900 outline-none focus:border-neutral-900">
              <option value="ready">Ready to bill · all dates</option>
              <option value="outstanding">Outstanding · all dates</option>
              <option value="settled">Settled · all dates</option>
            </select>
          </label>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start w-full">
        <div className="lg:col-span-8 space-y-3 w-full min-w-0">
          <ChamberBanner
            isToday={isToday}
            currentInChamber={currentInChamber || null}
            nextUpPatient={nextUpPatient || null}
            actionState={actionState}
            onComplete={handleRequestComplete}
            onSkip={(id) => {
              setActionState({ id, action: 'skip' });
              skipMutation.mutate(id, {
                onSettled: () => setActionState(null),
              });
            }}
            onMoveTomorrow={(id) => {
              setIsEndOfDayModalOpen(true);
            }}
            onCallNext={(id) => {
              setActionState({ id, action: 'call' });
              startConsultationMutation.mutate(id, {
                onSettled: () => setActionState(null),
              });
            }}
          />

          <QueueTable
            clinicTz={timezone}
            isLoading={isAppointmentsLoading}
            totalAppointmentsCount={appointments.length}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            queueCount={queueCount}
            expectedCount={expectedCount}
            completedCount={completedCount}
            paymentDueCount={paymentDueAppointments.length}
            allCount={dateAppointments.length}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            filteredAppointments={filteredAppointments}
            activeQueueAppointments={activeQueueList}
            expectedAppointments={expectedAppointments}
            completedAppointments={completedAppointments}
            paymentDueAppointments={paymentDueAppointments}
            isToday={isToday}
            dateLabel={dateLabel}
            actionState={actionState}
            collectingFeeId={collectingFeeId}
            setCollectingFeeId={setCollectingFeeId}
            activeMenuId={activeMenuId}
            setActiveMenuId={setActiveMenuId}
            onCollectFee={handleCollectFee}
            isCollectingFee={collectFeeMutation.isPending}
            onComplete={handleRequestComplete}
            onCall={(id) => {
              setActionState({ id, action: 'call' });
              startConsultationMutation.mutate(id, {
                onSettled: () => setActionState(null),
              });
            }}
            onSkip={(id) => {
              setActionState({ id, action: 'skip' });
              skipMutation.mutate(id, {
                onSettled: () => setActionState(null),
              });
            }}
            onReinsert={(id) => {
              setActionState({ id, action: 'reinsert' });
              reinsertMutation.mutate(id, {
                onSettled: () => setActionState(null),
              });
            }}
            onCheckIn={(item) => setCheckInAppointment(item)}
            onReschedule={(item) => handleOpenReschedule(item)}
            onBookReportReview={handleBookReportReview}
            onCancel={handleRequestCancel}
          />
        </div>

        <div className="lg:col-span-4 space-y-3 w-full min-w-0 lg:sticky lg:top-4">
          <ArrivalWindowsSidebar
            clinicSlots={clinicSlots}
            selectedDate={selectedDate}
            isToday={isToday}
            currentTime={currentTime}
            isOpen={clinicSlotsData?.is_open ?? false}
            closedReason={clinicSlotsData?.reason}
            closureDetails={clinicSlotsData?.closure}
            isLoading={isSlotsLoading}
            onBookSlot={(timeLabel) => {
              setBookingModalType('Pre-booked');
              setBookingInitialSlot(selectedDate, timeLabel);
              setBookingModalOpen(true);
            }}
            onJumpToDate={(d) => setSelectedDate(d)}
            onManageOverrides={() => router.push(`/clinic/schedule/history?type=all&date=${selectedDate}`)}
          />
        </div>
      </div>

      <RescheduleModal
        isOpen={isRescheduleModalOpen}
        appointment={rescheduleTarget}
        orgId={orgId}
        onClose={() => {
          setIsRescheduleModalOpen(false);
          setRescheduleTarget(null);
        }}
      />

      <EndOfDayModal
        isOpen={isEndOfDayModalOpen}
        orgId={orgId}
        patients={dateAppointments.filter((a) =>
          ['scheduled', 'arrived', 'skipped', 'in_progress'].includes(a.status)
        )}
        onClose={() => setIsEndOfDayModalOpen(false)}
      />

      {billTarget && <QuickBillModal isOpen onClose={() => setBillTarget(null)} patientName={billTarget.patient_name} patientPhone={billTarget.patient_phone} initialFee={billTarget.fee} initialBillItems={billTarget.bill_items} initialAmountPaid={billTarget.amount_paid} paymentReceipts={billTarget.payment_receipts} isSubmitting={collectFeeMutation.isPending} onCollect={async payload => {await collectFeeMutation.mutateAsync({appointmentId: billTarget.id, ...payload});}} />}
      <UrgentPatientModal
        isOpen={isUrgencyOpen}
        patients={activeQueueList.filter(patient => patient.status === 'arrived')}
        isSubmitting={isUrgencySubmitting}
        onClose={() => setIsUrgencyOpen(false)}
        onOpenWalkIn={() => {
          setIsUrgencyOpen(false);
          setBookingModalType('Walk-in');
          setBookingInitialSlot(null, null);
          setBookingModalOpen(true);
        }}
        onConfirm={async (appointmentId, reason) => {
          setIsUrgencySubmitting(true);
          try {
            await httpClient.post(`/api/v1/appointments/${appointmentId}/urgency`, { reason }, { orgId });
            await queryClient.invalidateQueries({ queryKey: ['clinic', 'queue', orgId] });
          } finally {
            setIsUrgencySubmitting(false);
          }
        }}
      />
      <PatientCheckInModal
        isOpen={Boolean(checkInAppointment)}
        appointment={checkInAppointment}
        onClose={() => setCheckInAppointment(null)}
        isSubmitting={arriveMutation.isPending}
        onConfirm={async (payload) => {
          await arriveMutation.mutateAsync({
            appointmentId: payload.appointmentId,
            data: {doctor_id: payload.doctor_id, patient_name: payload.patient_name, patient_phone: payload.patient_phone, dob: payload.dob, gender: payload.gender, blood_group: payload.blood_group, address: payload.address, reported_age: payload.reported_age, age_unit: payload.age_unit, chief_complaint: payload.chief_complaint},
          });
          setCheckInAppointment(null);
        }}
      />

      <ActionConfirmModal
        isOpen={Boolean(confirmModal)}
        title={confirmModal?.type === 'complete' ? 'Complete Consultation' : 'Cancel Appointment'}
        description={
          confirmModal?.type === 'complete'
            ? `Finalize the consultation for ${confirmModal.patientName}? This marks the patient visit as complete.`
            : `Are you sure you want to cancel the scheduled visit for ${confirmModal?.patientName}?`
        }
        confirmLabel={confirmModal?.type === 'complete' ? 'Complete Visit' : 'Yes, Cancel'}
        variant={confirmModal?.type === 'complete' ? 'emerald' : 'rose'}
        isSubmitting={Boolean(actionState?.action === 'complete')}
        onConfirm={handleExecuteConfirmAction}
        onClose={() => setConfirmModal(null)}
      />

      {undoToast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[70] bg-neutral-900 text-white px-4 py-2.5 rounded-2xl shadow-2xl border border-neutral-800 flex items-center gap-3 animate-in fade-in slide-in-from-bottom-3 duration-200 text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="font-medium">
              Consultation completed for <strong className="text-white">{undoToast.patientName}</strong>
            </span>
          </div>
          <div className="w-px h-4 bg-neutral-700 mx-1" />
          <button
            type="button"
            onClick={handleUndoCompletion}
            className="font-bold text-amber-300 hover:text-amber-200 transition-colors flex items-center gap-1 cursor-pointer"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Undo &amp; Reopen</span>
          </button>
          <button
            type="button"
            onClick={() => setUndoToast(null)}
            className="text-neutral-400 hover:text-white transition-colors cursor-pointer ml-1"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
