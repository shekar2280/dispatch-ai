'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Ban,
  AlertTriangle,
  AlertCircle,
  User,
  Phone,
  Clock,
  CheckCircle2,
  FileText,
  PhoneCall,
  Save,
  ArrowRight,
  ShieldAlert,
  ShieldCheck,
  Loader2,
  Stethoscope,
  Users,
  ChevronRight,
  Sparkles,
  Check,
  Coffee,
  RotateCcw,
  X,
  FlaskConical,
  CalendarClock,
  History,
  HeartPulse,
  Activity,
  Pill,
  Plus,
  Trash2,
  Receipt,
} from 'lucide-react';
import { useClinicStore } from './store';
import { ClinicLivePatient, BillItem } from './types';
import { useClinicDashboardQuery, useClinicBillingCatalogQuery } from './_hooks/useClinicQueries';
import {
  useSaveDoctorNotesMutation,
  useResolveEmergencyCallbackMutation,
  useUpdateAppointmentStatusMutation,
  useSkipPatientMutation,
} from './_hooks/useClinicMutations';

import { PatientHistoryDrawer } from './_components/PatientHistoryDrawer';
import { ActionConfirmModal } from './_components/ActionConfirmModal';
import { DashboardSkeleton } from './_components/ClinicSkeletons';

export default function ClinicDashboardPage() {
  const router = useRouter();
  const orgId = useClinicStore((s) => s.orgId);
  const isDayBlocked = useClinicStore((s) => s.isDayBlocked);
  const toggleDayEmergencyBlock = useClinicStore((s) => s.toggleDayEmergencyBlock);
  const activeRole = useClinicStore((s) => s.activeRole);

  const { data: dashboardData, isLoading: isDashboardLoading } = useClinicDashboardQuery(orgId);
  const saveDoctorNotesMutation = useSaveDoctorNotesMutation(orgId);
  const resolveEmergencyCallbackMutation = useResolveEmergencyCallbackMutation(orgId);
  const updateAppointmentStatusMutation = useUpdateAppointmentStatusMutation(orgId);
  const skipPatientMutation = useSkipPatientMutation(orgId);

  const { data: catalogData } = useClinicBillingCatalogQuery(orgId);
  const currencySymbol = catalogData?.currency_symbol || '';
  const [notes, setNotes] = useState('');
  const [diagnosis, setDiagnosis] = useState('');
  const [prescribedItems, setPrescribedItems] = useState<BillItem[]>([]);
  const [lastSavedNotes, setLastSavedNotes] = useState('');
  const [lastSavedDiagnosis, setLastSavedDiagnosis] = useState('');
  const [lastSavedPrescribedItems, setLastSavedPrescribedItems] = useState<BillItem[]>([]);
  const [selectedCatalogId, setSelectedCatalogId] = useState<string>('');
  const [itemQuantity, setItemQuantity] = useState<number>(1);
  const [resolvingSessionId, setResolvingSessionId] = useState<string | null>(null);
  const [historyDrawerPatient, setHistoryDrawerPatient] = useState<ClinicLivePatient | null>(null);
  const [showHistoryPanel, setShowHistoryPanel] = useState(true);

  const [actionConfirm, setActionConfirm] = useState<{
    type: 'complete' | 'cancel' | 'block';
    appointmentId?: string;
    patientName?: string;
  } | null>(null);
  const [activeAction, setActiveAction] = useState<{
    id: string;
    action: 'start' | 'complete' | 'cancel' | 'call' | 'block' | 'undo' | 'skip' | 'move_tomorrow';
  } | null>(null);
  const [undoToast, setUndoToast] = useState<{
    appointmentId: string;
    patientName: string;
  } | null>(null);

  const activePatient: ClinicLivePatient | null = dashboardData?.active_patient || null;
  const nextPatient: ClinicLivePatient | null = dashboardData?.next_patient || null;
  const waitingQueue: ClinicLivePatient[] = dashboardData?.waiting_queue || [];
  const emergencyCallbacks = dashboardData?.emergency_callbacks || [];
  const summary = dashboardData?.summary || {
    total_today: 0,
    completed_count: 0,
    in_room_count: 0,
    waiting_count: 0,
    no_show_count: 0,
    revenue_collected: 0,
    revenue_pending: 0,
  };

  const configuredFee = activePatient?.fee ?? catalogData?.consultation_fee;
  const baseConsultationFee = configuredFee == null ? undefined : Number(configuredFee);
  const prescribedMedicinesTotal = prescribedItems.reduce((acc, item) => acc + (Number(item.amount) || 0), 0);
  const totalCalculatedBill = baseConsultationFee == null ? undefined : baseConsultationFee + prescribedMedicinesTotal;

  const initializedAppointment = useRef<string | undefined>(undefined);

  useEffect(() => {
    const appointmentId = activePatient?.appointment_id;
    if (initializedAppointment.current === appointmentId) return;
    initializedAppointment.current = appointmentId;
    if (activePatient) {
      const initialNotes = activePatient.doctor_notes || '';
      const initialDiagnosis = activePatient.recent_diagnosis || '';
      const initialItems: BillItem[] = Array.isArray(activePatient.bill_items) ? activePatient.bill_items : [];
      setNotes(initialNotes);
      setDiagnosis(initialDiagnosis);
      setPrescribedItems(initialItems);
      setLastSavedNotes(initialNotes);
      setLastSavedDiagnosis(initialDiagnosis);
      setLastSavedPrescribedItems(initialItems);
    } else {
      setNotes('');
      setDiagnosis('');
      setPrescribedItems([]);
      setLastSavedNotes('');
      setLastSavedDiagnosis('');
      setLastSavedPrescribedItems([]);
    }
  }, [activePatient]);

  const itemsChanged = JSON.stringify(prescribedItems) !== JSON.stringify(lastSavedPrescribedItems);
  const hasContent = Boolean(notes.trim() || diagnosis.trim() || prescribedItems.length > 0);
  const hasUnsavedChanges =
    (notes.trim() !== lastSavedNotes.trim() ||
      diagnosis.trim() !== lastSavedDiagnosis.trim() ||
      itemsChanged) &&
    hasContent;
  const isNotesSaved = hasContent && !hasUnsavedChanges;

  const handleAddCatalogItem = () => {
    if (!selectedCatalogId || !catalogData?.billing_catalog) return;
    const found = catalogData.billing_catalog.find((c) => c.id === selectedCatalogId);
    if (!found) return;
    const qty = Math.max(1, Number(itemQuantity) || 1);
    const lineAmount = Number(found.unit_price) * qty;
    const newItem: BillItem = {
      id: `item-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: found.name,
      amount: lineAmount,
      category: found.category || 'medicine',
      quantity: qty,
      unit_price: found.unit_price,
    };
    setPrescribedItems((prev) => [...prev, newItem]);
    setSelectedCatalogId('');
    setItemQuantity(1);
  };

  const handleRemovePrescribedItem = (index: number) => {
    setPrescribedItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSaveNotes = async () => {
    if (!activePatient) return;
    const cleanNotes = notes.trim();
    const cleanDiagnosis = diagnosis.trim();
    if (!cleanNotes && !cleanDiagnosis && prescribedItems.length === 0) return;
    try {
      await saveDoctorNotesMutation.mutateAsync({
        appointmentId: activePatient.appointment_id,
        doctorNotes: cleanNotes,
        recentDiagnosis: cleanDiagnosis,
        billItems: prescribedItems,
        fee: totalCalculatedBill,
      });
      setLastSavedNotes(cleanNotes);
      setLastSavedDiagnosis(cleanDiagnosis);
      setLastSavedPrescribedItems(prescribedItems);
    } catch { }
  };

  const handleStartConsultation = async () => {
    if (!activePatient) return;
    const apptId = activePatient.appointment_id;
    setActiveAction({ id: apptId, action: 'start' });
    try {
      await updateAppointmentStatusMutation.mutateAsync({
        appointmentId: apptId,
        status: 'in_progress',
      });
    } finally {
      setActiveAction(null);
    }
  };

  const handleCallInPatient = async (appointmentId: string) => {
    setActiveAction({ id: appointmentId, action: 'call' });
    try {
      await updateAppointmentStatusMutation.mutateAsync({
        appointmentId,
        status: 'in_progress',
      });
      setShowHistoryPanel(false);
    } finally {
      setActiveAction(null);
    }
  };

  const handleStepOut = async () => {
    if (!activePatient) return;
    const apptId = activePatient.appointment_id;
    setActiveAction({ id: apptId, action: 'skip' });
    try {
      const promises: Promise<any>[] = [skipPatientMutation.mutateAsync(apptId)];
      if (notes.trim() || diagnosis.trim() || prescribedItems.length > 0) {
        promises.push(
          saveDoctorNotesMutation.mutateAsync({
            appointmentId: apptId,
            doctorNotes: notes.trim(),
            recentDiagnosis: diagnosis.trim(),
            billItems: prescribedItems,
            fee: totalCalculatedBill,
          }).catch(() => {})
        );
      }
      if (nextPatient) {
        promises.push(
          updateAppointmentStatusMutation.mutateAsync({
            appointmentId: nextPatient.appointment_id,
            status: 'in_progress',
          }).catch(() => {})
        );
      }
      await Promise.all(promises);
    } finally {
      setActiveAction(null);
    }
  };

  const handleMoveTomorrow = async () => {
    if (!activePatient) return;
    const apptId = activePatient.appointment_id;
    setActiveAction({ id: apptId, action: 'move_tomorrow' });
    try {
      if (notes.trim() || diagnosis.trim() || prescribedItems.length > 0) {
        try {
          await saveDoctorNotesMutation.mutateAsync({
            appointmentId: apptId,
            doctorNotes: notes.trim(),
            recentDiagnosis: diagnosis.trim(),
            billItems: prescribedItems,
            fee: totalCalculatedBill,
          });
        } catch { }
      }
      router.push('/clinic/schedule');
    } finally {
      setActiveAction(null);
    }
  };

  const handleUndoCompletion = async () => {
    if (!undoToast) return;
    setActiveAction({ id: undoToast.appointmentId, action: 'undo' });
    try {
      await updateAppointmentStatusMutation.mutateAsync({
        appointmentId: undoToast.appointmentId,
        status: 'in_progress',
      });
      setUndoToast(null);
    } finally {
      setActiveAction(null);
    }
  };

  const executeConfirmAction = async () => {
    if (!actionConfirm) return;
    if (actionConfirm.type === 'complete' && activePatient) {
      const patientId = activePatient.appointment_id;
      const patientName = activePatient.patient_name;
      setActiveAction({ id: patientId, action: 'complete' });
      try {
        const cleanNotes = notes.trim();
        const cleanDiagnosis = diagnosis.trim();
        if (cleanNotes || cleanDiagnosis || prescribedItems.length > 0) {
          try {
            await saveDoctorNotesMutation.mutateAsync({
              appointmentId: patientId,
              doctorNotes: cleanNotes,
              recentDiagnosis: cleanDiagnosis,
              billItems: prescribedItems,
              fee: totalCalculatedBill,
            });
            setLastSavedNotes(cleanNotes);
            setLastSavedDiagnosis(cleanDiagnosis);
            setLastSavedPrescribedItems(prescribedItems);
          } catch { }
        }
        await updateAppointmentStatusMutation.mutateAsync({
          appointmentId: patientId,
          status: 'completed',
        });
        if (nextPatient) {
          await updateAppointmentStatusMutation.mutateAsync({
            appointmentId: nextPatient.appointment_id,
            status: 'in_progress',
          });
        }
        setUndoToast({ appointmentId: patientId, patientName });
      } finally {
        setActiveAction(null);
        setActionConfirm(null);
      }
    } else if (actionConfirm.type === 'cancel' && actionConfirm.appointmentId) {
      const apptId = actionConfirm.appointmentId;
      setActiveAction({ id: apptId, action: 'cancel' });
      try {
        await updateAppointmentStatusMutation.mutateAsync({
          appointmentId: apptId,
          status: 'cancelled',
        });
      } finally {
        setActiveAction(null);
        setActionConfirm(null);
      }
    } else if (actionConfirm.type === 'block') {
      setActiveAction({ id: 'block-day', action: 'block' });
      try {
        toggleDayEmergencyBlock();
      } finally {
        setActiveAction(null);
        setActionConfirm(null);
      }
    }
  };

  const handleResolveCallback = async (sessionId: string) => {
    setResolvingSessionId(sessionId);
    try {
      await resolveEmergencyCallbackMutation.mutateAsync(sessionId);
    } finally {
      setResolvingSessionId(null);
    }
  };

  const upcomingQueue = waitingQueue.filter(
    (p) => p.appointment_id !== activePatient?.appointment_id && p.appointment_id !== nextPatient?.appointment_id
  );

  const allergiesText = activePatient ? (
    Array.isArray(activePatient.allergies)
      ? activePatient.allergies.filter(Boolean).join(', ')
      : (activePatient.allergies && activePatient.allergies !== 'N/A' && activePatient.allergies !== 'None' ? String(activePatient.allergies).trim() : '')
  ) : '';

  const chronicText = activePatient ? (
    Array.isArray(activePatient.chronic_conditions)
      ? activePatient.chronic_conditions.filter(Boolean).join(', ')
      : (activePatient.chronic_conditions && activePatient.chronic_conditions !== 'N/A' && activePatient.chronic_conditions !== 'None' ? String(activePatient.chronic_conditions).trim() : '')
  ) : '';

  const isQueueCompletelyEmpty = !nextPatient && upcomingQueue.length === 0;

  if (isDashboardLoading && !dashboardData) {
    return <DashboardSkeleton />;
  }

  return (
    <div className="min-h-full flex flex-col gap-4 font-sans text-neutral-900 pb-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg font-bold tracking-tight text-neutral-950">
              Consultation Desk
            </h1>
          </div>
          <p className="text-xs text-neutral-500 mt-0.5 font-normal">
            Active patient chamber, quick clinical notes, and live queue management
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          {nextPatient ? (
            <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-neutral-100 border border-neutral-200 text-neutral-800 shadow-2xs">
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
              <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wide">Next:</span>
              <span className="text-xs font-bold text-neutral-900 truncate max-w-[130px]">
                {nextPatient.patient_name}
              </span>
              <span className="text-neutral-300">•</span>
              <span className="text-[11px] font-medium text-neutral-600">
                {nextPatient.age || 'Age --'}
              </span>
              {activeRole === 'doctor' && (
                <button
                  type="button"
                  disabled={activeAction?.id === nextPatient.appointment_id}
                  onClick={() => handleCallInPatient(nextPatient.appointment_id)}
                  className="ml-1 inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-white hover:bg-neutral-50 text-neutral-900 border border-neutral-200 text-[11px] font-semibold transition-all shadow-2xs cursor-pointer disabled:opacity-60"
                >
                  {activeAction?.id === nextPatient.appointment_id && activeAction.action === 'call' ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : null}
                  <span>Call In</span>
                  <ArrowRight className="w-3 h-3 text-neutral-500" />
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-neutral-200 text-xs font-medium text-neutral-600 shadow-2xs">
              <Coffee className="w-3.5 h-3.5 text-neutral-400" />
              <span>Next: Queue Empty</span>
            </div>
          )}

          <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white border border-neutral-200/80 shadow-2xs text-xs font-medium text-neutral-600">
            <div className="flex items-center gap-1.5">
              <span className="text-neutral-400">Total</span>
              <span className="font-bold text-neutral-900 text-xs">{summary.total_today}</span>
            </div>
            <div className="w-px h-3.5 bg-neutral-200 mx-1" />
            <div className="flex items-center gap-1.5">
              <span className="text-neutral-400">Seen</span>
              <span className="font-bold text-emerald-600 text-xs">{summary.completed_count}</span>
            </div>
            <div className="w-px h-3.5 bg-neutral-200 mx-1" />
            <div className="flex items-center gap-1.5">
              <span className="text-neutral-400">Waiting</span>
              <span className="font-bold text-amber-600 text-xs">{summary.waiting_count}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              if (isDayBlocked) {
                toggleDayEmergencyBlock();
              } else {
                setActionConfirm({ type: 'block' });
              }
            }}
            disabled={activeAction?.action === 'block'}
            className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all shadow-2xs cursor-pointer disabled:opacity-60 ${isDayBlocked
              ? 'bg-rose-600 hover:bg-rose-700 text-white'
              : 'bg-white border border-rose-200 text-rose-600 hover:bg-rose-50'
              }`}
          >
            {activeAction?.action === 'block' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Ban className="w-3.5 h-3.5" />
            )}
            <span>{isDayBlocked ? 'Resume OPD' : 'Block Remainder of Day'}</span>
          </button>
        </div>
      </div>

      {isDayBlocked && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-rose-100 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-4 h-4 text-rose-600" />
            </div>
            <p className="text-sm font-medium text-rose-900">
              OPD Booking Halted: AI Receptionist is notifying callers that clinic schedule is closed for today.
            </p>
          </div>
          <button
            type="button"
            onClick={toggleDayEmergencyBlock}
            className="text-xs font-semibold text-rose-700 hover:text-rose-800 bg-white px-3 py-1.5 rounded-lg border border-rose-200 shadow-sm transition-colors"
          >
            Reopen Schedule
          </button>
        </div>
      )}

      {emergencyCallbacks.length > 0 && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 shadow-sm flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-600 animate-pulse" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-rose-900 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-rose-600" />
                <span>Urgent Emergency Escalations ({emergencyCallbacks.length})</span>
              </h2>
            </div>
            <span className="text-xs font-semibold text-rose-700 bg-rose-100 px-2.5 py-1 rounded-md">Immediate Action Required</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {emergencyCallbacks.map((callback) => (
              <div
                key={callback.session_id}
                className="p-4 rounded-xl bg-white border border-rose-100 shadow-sm flex flex-col justify-between gap-3"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-bold text-neutral-900">{callback.caller_phone}</span>
                    <span className="text-xs font-medium text-neutral-500 bg-neutral-50 px-2 py-0.5 rounded-md border border-neutral-100">{callback.call_time}</span>
                  </div>
                  <p className="text-sm text-neutral-700 font-medium leading-relaxed">
                    {callback.emergency_reason}
                  </p>
                  {callback.transcript_snippet && (
                    <p className="text-xs text-neutral-500 italic mt-2 bg-neutral-50 p-2.5 rounded-lg border border-neutral-100">
                      &quot;{callback.transcript_snippet}&quot;
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 pt-3 border-t border-neutral-100 mt-2">
                  <a
                    href={`tel:${callback.caller_phone}`}
                    className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-black text-white text-xs font-semibold hover:bg-neutral-800 transition-colors shadow-sm"
                  >
                    <PhoneCall className="w-4 h-4" />
                    <span>Call Back</span>
                  </a>
                  <button
                    type="button"
                    disabled={resolvingSessionId === callback.session_id}
                    onClick={() => handleResolveCallback(callback.session_id)}
                    className="px-4 py-2 rounded-xl bg-white border border-neutral-200 text-neutral-700 text-xs font-semibold hover:bg-neutral-50 hover:border-neutral-300 transition-all disabled:opacity-50 shadow-sm"
                  >
                    {resolvingSessionId === callback.session_id ? 'Resolving...' : 'Resolve'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4 flex-1">
        <div className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-5 shadow-sm flex flex-col">
          {isDashboardLoading && !dashboardData ? (
            <div className="min-h-[320px] flex flex-col items-center justify-center text-neutral-400 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-neutral-300" />
              <p className="text-sm font-medium">Syncing room status...</p>
            </div>
          ) : activePatient ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-neutral-100 pb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-bold text-neutral-950 truncate tracking-tight">
                      {activePatient.patient_name}
                    </h3>
                    <div className="flex items-center gap-1.5 text-xs text-neutral-600 flex-wrap">
                      <span className="font-semibold text-neutral-800 bg-neutral-100 px-2 py-0.5 rounded border border-neutral-200 shadow-2xs">
                        {activePatient.age || 'Age --'}
                      </span>
                      <span className="text-neutral-300">•</span>
                      <span>{activePatient.gender || 'Gender --'}</span>
                      {activePatient.blood_group && activePatient.blood_group !== 'N/A' && (
                        <>
                          <span className="text-neutral-300">•</span>
                          <span className="font-bold text-rose-700 bg-rose-50 border border-rose-200 px-1.5 py-0.5 rounded font-mono text-[11px]">
                            {activePatient.blood_group}
                          </span>
                        </>
                      )}
                      {allergiesText && (
                        <>
                          <span className="text-neutral-300">•</span>
                          <span className="font-semibold text-rose-800 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded text-[11px] flex items-center gap-1">
                            <AlertCircle className="w-3 h-3 text-rose-600 shrink-0" />
                            Allergies: {allergiesText}
                          </span>
                        </>
                      )}
                      {chronicText && (
                        <>
                          <span className="text-neutral-300">•</span>
                          <span className="font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded text-[11px]">
                            Chronic: {chronicText}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-xs">
                    <span className="text-neutral-400 font-medium">Reason for Visit:</span>
                    <span className="font-semibold text-neutral-800">{activePatient.chief_complaint || 'General routine consultation'}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap shrink-0">
                  {activeRole === 'doctor' ? (
                    <>
                      {activePatient.status !== 'in_progress' && activePatient.status !== 'completed' && (
                        <button
                          type="button"
                          onClick={handleStartConsultation}
                          disabled={activeAction?.id === activePatient.appointment_id}
                          className="px-3 h-8 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-semibold transition-colors shadow-2xs cursor-pointer flex items-center gap-1.5 disabled:opacity-60"
                        >
                          {activeAction?.id === activePatient.appointment_id && activeAction.action === 'start' ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Stethoscope className="w-3.5 h-3.5" />
                          )}
                          <span>Start Consultation</span>
                        </button>
                      )}

                      {activePatient.status === 'in_progress' && (
                        <>
                          <button
                            type="button"
                            onClick={() => setActionConfirm({ type: 'complete', appointmentId: activePatient.appointment_id, patientName: activePatient.patient_name })}
                            disabled={Boolean(activeAction)}
                            className="px-3 h-8 rounded-lg bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold transition-all shadow-xs cursor-pointer flex items-center gap-1.5 disabled:opacity-60"
                          >
                            {activeAction?.id === activePatient.appointment_id && activeAction.action === 'complete' ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                            )}
                            <span>End Consultation</span>
                          </button>

                          <button
                            type="button"
                            onClick={handleStepOut}
                            disabled={Boolean(activeAction)}
                            className="px-2.5 h-8 rounded-lg border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-900 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5 disabled:opacity-60"
                            title="Patient stepped out for lab tests / vitals"
                          >
                            {activeAction?.id === activePatient.appointment_id && activeAction.action === 'skip' ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-700" />
                            ) : (
                              <FlaskConical className="w-3.5 h-3.5 text-amber-700" />
                            )}
                            <span>Step Out for Lab</span>
                          </button>

                          <button
                            type="button"
                            onClick={handleMoveTomorrow}
                            disabled={Boolean(activeAction)}
                            className="px-2.5 h-8 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-neutral-700 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5 disabled:opacity-60"
                            title="Review reports tomorrow"
                          >
                            {activeAction?.id === activePatient.appointment_id && activeAction.action === 'move_tomorrow' ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-500" />
                            ) : (
                              <CalendarClock className="w-3.5 h-3.5 text-neutral-500" />
                            )}
                            <span>Plan Tomorrow</span>
                          </button>
                        </>
                      )}
                    </>
                  ) : (
                    <span className="px-3 h-8 rounded-lg bg-neutral-100 text-neutral-700 border border-neutral-200 text-xs font-semibold flex items-center gap-1.5">
                      Doctor in Chamber
                    </span>
                  )}

                  <button
                    type="button"
                    onClick={() => setShowHistoryPanel(!showHistoryPanel)}
                    className="px-2.5 h-8 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-neutral-600 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5 ml-1 shadow-2xs"
                  >
                    <History className="w-3.5 h-3.5 text-neutral-500" />
                    <span>{showHistoryPanel ? 'Hide Past Visits' : 'Past Visits'}</span>
                  </button>
                </div>
              </div>

              <div className={`grid grid-cols-1 ${showHistoryPanel ? 'lg:grid-cols-2' : ''} gap-4 items-stretch`}>
                <div className="rounded-xl border border-neutral-200 bg-neutral-50/40 p-3.5 sm:p-4 shadow-2xs flex flex-col justify-between gap-3">
                  <div className="flex items-center justify-between border-b border-neutral-200/80 pb-2 shrink-0">
                    <label className="text-xs font-bold text-neutral-900 flex items-center gap-1.5 uppercase tracking-wider">
                      <FileText className="w-3.5 h-3.5 text-neutral-500" />
                      <span>Doctor&apos;s Advice &amp; Prescription</span>
                    </label>
                    {hasUnsavedChanges && (
                      <span className="text-[10px] font-semibold text-amber-700 flex items-center gap-1 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        Unsaved Changes
                      </span>
                    )}
                  </div>

                  <div className="flex flex-col gap-2.5 flex-1 min-h-0">
                    <input
                      type="text"
                      value={diagnosis}
                      onChange={(e) => setDiagnosis(e.target.value)}
                      placeholder="Diagnosis or Main Symptoms (e.g. Viral Fever, Acute Pharyngitis)..."
                      className="w-full text-xs font-medium px-3 h-8.5 rounded-lg border border-neutral-200 bg-white focus:outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 shadow-2xs transition-all placeholder:text-neutral-400 shrink-0"
                    />

                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Doctor's clinical notes, dosages, follow-up instructions, or diet advice..."
                      rows={2}
                      className="w-full text-xs font-medium p-2.5 rounded-lg border border-neutral-200 bg-white focus:outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 shadow-2xs transition-all leading-relaxed placeholder:text-neutral-400 resize-none shrink-0"
                    />

                    <div className="rounded-lg border border-neutral-200 bg-white p-2.5 shadow-2xs space-y-2">
                      <div className="flex items-center justify-between border-b border-neutral-100 pb-1.5">
                        <div className="flex items-center gap-1.5">
                          <Pill className="w-3.5 h-3.5 text-neutral-600" />
                          <span className="text-xs font-bold text-neutral-900">Prescribe Medicines &amp; Services</span>
                        </div>
                        <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-neutral-100 text-neutral-600">
                          {prescribedItems.length} {prescribedItems.length === 1 ? 'item' : 'items'} • {currencySymbol}{prescribedMedicinesTotal}
                        </span>
                      </div>

                      <div className="grid grid-cols-[1fr_60px_auto] gap-2 items-center">
                        <select
                          value={selectedCatalogId}
                          onChange={(e) => setSelectedCatalogId(e.target.value)}
                          className="h-8 rounded-lg border border-neutral-200 bg-neutral-50/50 px-2.5 text-xs text-neutral-800 focus:outline-none focus:border-neutral-950 focus:bg-white"
                        >
                          <option value="">-- Select medicine or service --</option>
                          {catalogData?.billing_catalog?.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name} ({currencySymbol}{item.unit_price})
                            </option>
                          ))}
                        </select>
                        <input
                          type="number"
                          min={1}
                          value={itemQuantity}
                          onChange={(e) => setItemQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                          className="h-8 rounded-lg border border-neutral-200 px-1.5 text-xs text-center focus:outline-none focus:border-neutral-950"
                          placeholder="Qty"
                        />
                        <button
                          type="button"
                          onClick={handleAddCatalogItem}
                          disabled={!selectedCatalogId}
                          className="h-8 px-3 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-semibold inline-flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>Add</span>
                        </button>
                      </div>

                      {prescribedItems.length > 0 && (
                        <div className="divide-y divide-neutral-100 border border-neutral-100 rounded-lg overflow-hidden max-h-[100px] overflow-y-auto">
                          {prescribedItems.map((item, index) => (
                            <div key={item.id || index} className="p-1.5 px-2 flex items-center justify-between text-xs bg-neutral-50/30 hover:bg-neutral-50">
                              <div className="flex flex-col min-w-0 pr-2">
                                <span className="font-semibold text-neutral-900 truncate text-[11px]">{item.name}</span>
                                <span className="text-[10px] text-neutral-500 font-mono">
                                  {item.quantity} × {currencySymbol}{item.unit_price || (item.amount / (item.quantity || 1))}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <span className="font-bold text-neutral-900 font-mono text-xs">{currencySymbol}{item.amount}</span>
                                <button
                                  type="button"
                                  onClick={() => handleRemovePrescribedItem(index)}
                                  className="text-neutral-400 hover:text-rose-600 p-1 rounded hover:bg-rose-50 cursor-pointer"
                                  title="Remove item"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="flex items-center justify-between pt-1 border-t border-neutral-100 text-xs">
                        <div className="flex items-center gap-2 text-neutral-500 text-[11px]">
                          <span>Consult: {currencySymbol}{baseConsultationFee}</span>
                          <span>+</span>
                          <span>Medicines: {currencySymbol}{prescribedMedicinesTotal}</span>
                        </div>
                        <div className="flex items-center gap-1 font-bold text-neutral-900">
                          <Receipt className="w-3.5 h-3.5 text-neutral-500" />
                          <span>Total: {currencySymbol}{totalCalculatedBill}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-end shrink-0 pt-0.5">
                      {saveDoctorNotesMutation.isPending ? (
                        <div className="inline-flex items-center gap-1.5 px-3 h-8 rounded-lg bg-neutral-900 text-white text-xs font-semibold shadow-2xs">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Saving...</span>
                        </div>
                      ) : isNotesSaved ? (
                        <div className="inline-flex items-center gap-1.5 px-3 h-8 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold shadow-2xs">
                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Saved</span>
                        </div>
                      ) : (
                        <button
                          type="button"
                          disabled={!hasContent}
                          onClick={handleSaveNotes}
                          className="inline-flex items-center gap-1.5 px-3.5 h-8 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-semibold transition-all shadow-2xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Save className="w-3.5 h-3.5" />
                          <span>Save Notes &amp; Prescription</span>
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {showHistoryPanel && (
                  <div className="rounded-xl border border-neutral-200 bg-neutral-50/40 p-3.5 sm:p-4 shadow-2xs flex flex-col justify-between gap-3">
                    <div className="flex items-center justify-between border-b border-neutral-200/80 pb-2 shrink-0">
                      <div className="flex items-center gap-1.5">
                        <History className="w-3.5 h-3.5 text-neutral-500" />
                        <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-900">
                          Previous Visits &amp; Records
                        </h4>
                      </div>
                      {activePatient.previous_visits && activePatient.previous_visits.length > 0 && (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-700">
                          {activePatient.previous_visits.length} Past Visits
                        </span>
                      )}
                    </div>

                    <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2 max-h-[360px]">
                      {activePatient.previous_visits && activePatient.previous_visits.length > 0 ? (
                        activePatient.previous_visits.map((visit) => (
                          <div
                            key={visit.appointment_id}
                            className="p-2.5 rounded-lg bg-white border border-neutral-200 shadow-2xs space-y-1"
                          >
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-bold text-neutral-900">{visit.date}</span>
                            </div>
                            {visit.recent_diagnosis && (
                              <p className="text-[11px] font-semibold text-neutral-800">
                                <span className="text-neutral-400 font-normal">Diagnosis:</span> {visit.recent_diagnosis}
                              </p>
                            )}
                            {visit.chief_complaint && !visit.recent_diagnosis && (
                              <p className="text-[11px] text-neutral-600 font-medium">
                                <span className="text-neutral-400">Complaint:</span> {visit.chief_complaint}
                              </p>
                            )}
                            {visit.doctor_notes && (
                              <div className="p-2 rounded bg-neutral-50 text-[11px] text-neutral-800 font-mono leading-relaxed border border-neutral-100">
                                {visit.doctor_notes}
                              </div>
                            )}
                          </div>
                        ))
                      ) : (
                        <div className="py-8 flex flex-col items-center justify-center p-4 text-center rounded-lg bg-white border border-neutral-200/80">
                          <History className="w-4 h-4 text-neutral-400 mb-1" />
                          <p className="text-xs font-bold text-neutral-800">First Visit</p>
                          <p className="text-[11px] text-neutral-500 mt-0.5">
                            No previous visits recorded in clinic system.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="min-h-[400px] flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-neutral-200 bg-neutral-50/40 p-8">
              <div className="w-14 h-14 rounded-full bg-white border border-neutral-200 flex items-center justify-center text-neutral-400 shadow-2xs">
                <Stethoscope className="w-7 h-7" />
              </div>
              <div className="text-center">
                <h3 className="text-base font-bold text-neutral-900 mb-1">Chamber is Ready</h3>
                <p className="text-xs font-medium text-neutral-500 max-w-sm mx-auto">
                  No patient currently in consultation. Call in the next waiting patient from the queue outside.
                </p>
              </div>
              {nextPatient && (
                <button
                  type="button"
                  disabled={activeAction?.id === nextPatient.appointment_id}
                  onClick={() => handleCallInPatient(nextPatient.appointment_id)}
                  className="mt-2 inline-flex items-center gap-2 px-5 h-10 rounded-xl bg-neutral-900 hover:bg-black text-white text-xs font-bold transition-all shadow-xs cursor-pointer disabled:opacity-60"
                >
                  {activeAction?.id === nextPatient.appointment_id && activeAction.action === 'call' ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : null}
                  <span>Call In {nextPatient.patient_name} ({nextPatient.age || 'Age --'})</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <PatientHistoryDrawer
        isOpen={Boolean(historyDrawerPatient)}
        onClose={() => setHistoryDrawerPatient(null)}
        patient={historyDrawerPatient}
      />

      <ActionConfirmModal
        isOpen={Boolean(actionConfirm)}
        title={
          actionConfirm?.type === 'complete'
            ? 'Complete Consultation'
            : actionConfirm?.type === 'cancel'
              ? 'Cancel Appointment'
              : 'Block Remainder of Day'
        }
        description={
          actionConfirm?.type === 'complete'
            ? `Complete the consultation for ${actionConfirm.patientName || 'this patient'}? Clinical notes and diagnosis will be saved to medical records, and the next patient will be called.`
            : actionConfirm?.type === 'cancel'
              ? `Are you sure you want to cancel the appointment for ${actionConfirm?.patientName || 'this patient'}? This removes them from today's active schedule.`
              : 'Are you sure you want to block the remainder of today? Tulsi will immediately inform all incoming callers that OPD is closed for today.'
        }
        confirmLabel={
          actionConfirm?.type === 'complete'
            ? 'Complete & Call Next'
            : actionConfirm?.type === 'cancel'
              ? 'Yes, Cancel Visit'
              : 'Block OPD Today'
        }
        variant={
          actionConfirm?.type === 'complete'
            ? 'emerald'
            : actionConfirm?.type === 'cancel'
              ? 'rose'
              : 'rose'
        }
        isSubmitting={Boolean(activeAction)}
        onConfirm={executeConfirmAction}
        onClose={() => setActionConfirm(null)}
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
            disabled={activeAction?.action === 'undo'}
            onClick={handleUndoCompletion}
            className="font-bold text-amber-300 hover:text-amber-200 transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
          >
            {activeAction?.action === 'undo' ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RotateCcw className="w-3 h-3" />
            )}
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
