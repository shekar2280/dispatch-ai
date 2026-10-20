'use client';

import React, { useState, useMemo, useEffect } from 'react';
import {
  Check,
  Clock3,
  RotateCcw,
  X,
  Calendar,
  Sparkles,
  Sun,
  Ban,
  Loader2,
  ArrowRight,
} from 'lucide-react';
import { AppointmentItem } from '../../types';
import {
  useBatchReconcileQueueMutation,
  BatchReconciliationItem,
} from '../../_hooks/useClinicMutations';
import { useClinicSlotsQuery } from '../../_hooks/useClinicQueries';
import { formatDateISO, addDaysISO } from '../../utils';

interface EndOfDayModalProps {
  isOpen: boolean;
  orgId?: string | null;
  patients: AppointmentItem[];
  onClose: () => void;
}

type ReconciliationActionType =
  | 'rollover_morning'
  | 'rollover_same_time'
  | 'custom_time'
  | 'cancel';

interface StagedReconciliationItem {
  action: ReconciliationActionType;
  targetDate: string;
  targetTime: string;
  patientConfirmed: boolean;
}

export function EndOfDayModal({
  isOpen,
  orgId,
  patients,
  onClose,
}: EndOfDayModalProps) {
  const tomorrowStr = useMemo(() => addDaysISO(formatDateISO(new Date()), 1), []);
  const batchMutation = useBatchReconcileQueueMutation(orgId);

  const { data: tomorrowSlotsData } = useClinicSlotsQuery(
    orgId,
    isOpen ? tomorrowStr : null
  );

  const tomorrowSlots = useMemo(() => {
    return (tomorrowSlotsData?.slots || []).filter(
      (s) => s.is_available && s.status_type === 'AVAILABLE' && s.window_state !== 'CLOSED'
    );
  }, [tomorrowSlotsData]);

  const [stagedMap, setStagedMap] = useState<Record<string, StagedReconciliationItem>>({});
  const [expandedCustomId, setExpandedCustomId] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || patients.length === 0) return;
    const initialMap: Record<string, StagedReconciliationItem> = {};
    const defaultMorningTime = tomorrowSlots[0]?.time_label || '10:00 AM';

    patients.forEach((p) => {
      const hasSpecificTime = Boolean(p.appointment_time);
      initialMap[p.id] = {
        action: hasSpecificTime ? 'rollover_same_time' : 'rollover_morning',
        targetDate: tomorrowStr,
        targetTime: p.appointment_time || defaultMorningTime,
        patientConfirmed: false,
      };
    });
    setStagedMap(initialMap);
  }, [isOpen, patients, tomorrowStr, tomorrowSlots]);

  const setAllAction = (action: ReconciliationActionType) => {
    const defaultMorningTime = tomorrowSlots[0]?.time_label || '10:00 AM';
    setStagedMap((prev) => {
      const next: Record<string, StagedReconciliationItem> = {};
      patients.forEach((p) => {
        next[p.id] = {
          action,
          targetDate: tomorrowStr,
          targetTime:
            action === 'rollover_same_time'
              ? p.appointment_time || defaultMorningTime
              : defaultMorningTime,
          patientConfirmed: false,
        };
      });
      return next;
    });
    setExpandedCustomId(null);
  };

  const updateItem = (
    patientId: string,
    updates: Partial<StagedReconciliationItem>
  ) => {
    setStagedMap((prev) => ({
      ...prev,
      [patientId]: {
        ...(prev[patientId] || {
          action: 'rollover_morning',
          targetDate: tomorrowStr,
          targetTime: tomorrowSlots[0]?.time_label || '10:00 AM',
          patientConfirmed: false,
        }),
        ...updates,
      },
    }));
  };

  const rolloverCount = useMemo(() => {
    return Object.values(stagedMap).filter((item) => item.action !== 'cancel').length;
  }, [stagedMap]);

  const cancelCount = useMemo(() => {
    return Object.values(stagedMap).filter((item) => item.action === 'cancel').length;
  }, [stagedMap]);

  const handleExecuteReconciliation = async () => {
    const actions: BatchReconciliationItem[] = patients.map((p) => {
      const item = stagedMap[p.id] || {
        action: 'rollover_morning',
        targetDate: tomorrowStr,
        targetTime: tomorrowSlots[0]?.time_label || '10:00 AM',
      };
      return {
        appointment_id: p.id,
        action: item.action,
        target_date: item.action === 'cancel' ? undefined : item.targetDate,
        target_time: item.action === 'cancel' ? undefined : item.targetTime,
        patient_confirmed: item.action !== 'cancel' && item.patientConfirmed,
      };
    });

    await batchMutation.mutateAsync({ actions });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-neutral-950/60 p-3 sm:p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-4xl rounded-2xl border border-neutral-200 bg-white shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        <div className="flex items-center justify-between border-b border-neutral-100 px-6 py-4 bg-neutral-50/70">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-base font-bold text-neutral-900 tracking-tight">
                End of Day Wrap-Up
              </h2>
              <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-amber-100/80 text-amber-900 border border-amber-300">
                {patients.length} remaining
              </span>
            </div>
            <p className="mt-0.5 text-xs text-neutral-500">
              Move unseen patients to tomorrow morning, keep same times, or cancel appointments.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-xl text-neutral-400 hover:bg-neutral-200/60 hover:text-black transition-colors cursor-pointer"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {patients.length > 0 && (
          <div className="px-6 py-3 bg-neutral-50/90 border-b border-neutral-200/80 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-neutral-500">
                Quick Presets:
              </span>
              <span className="text-xs text-neutral-400">Apply to all {patients.length} patients</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setAllAction('rollover_morning')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-neutral-200 bg-white hover:border-amber-400 hover:bg-amber-50/60 text-neutral-800 transition-all shadow-2xs cursor-pointer"
              >
                <Sun className="w-3.5 h-3.5 text-amber-500" />
                <span>All Morning (10 AM+)</span>
              </button>
              <button
                type="button"
                onClick={() => setAllAction('rollover_same_time')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-neutral-200 bg-white hover:border-indigo-400 hover:bg-indigo-50/60 text-neutral-800 transition-all shadow-2xs cursor-pointer"
              >
                <Clock3 className="w-3.5 h-3.5 text-indigo-500" />
                <span>All Keep Same Time</span>
              </button>
              <button
                type="button"
                onClick={() => setAllAction('cancel')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-neutral-200 bg-white hover:border-rose-400 hover:bg-rose-50/60 text-neutral-800 transition-all shadow-2xs cursor-pointer"
              >
                <Ban className="w-3.5 h-3.5 text-rose-500" />
                <span>All Cancel</span>
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-[#FBF9F5]/40">
          {patients.length === 0 ? (
            <div className="py-16 text-center text-sm text-neutral-400">
              No waiting patients remaining today.
            </div>
          ) : (
            patients.map((patient) => {
              const currentStaged = stagedMap[patient.id] || {
                action: 'rollover_morning',
                targetDate: tomorrowStr,
                targetTime: patient.appointment_time || '10:00 AM',
                patientConfirmed: false,
              };

              const isCustom = currentStaged.action === 'custom_time';
              const isExpanded = expandedCustomId === patient.id;
              const isCancel = currentStaged.action === 'cancel';

              return (
                <div
                  key={patient.id}
                  className={`rounded-2xl border transition-all shadow-2xs ${isCancel
                    ? 'border-rose-200/90 bg-rose-50/25'
                    : 'border-neutral-200/90 bg-white hover:border-neutral-300'
                    } p-4 space-y-3`}
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-neutral-900 truncate">
                          {patient.patient_name}
                        </span>
                        <span className="font-mono text-xs text-neutral-400 shrink-0">
                          {patient.patient_phone}
                        </span>
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border shrink-0 ${patient.token_prefix === 'R'
                            ? 'bg-purple-50 text-purple-800 border-purple-200'
                            : patient.token_number !== null
                              ? 'bg-amber-50 text-amber-800 border-amber-200'
                              : 'bg-neutral-100 text-neutral-700 border-neutral-200'
                            }`}
                        >
                          {patient.display_token || patient.appointment_time || 'Slot'}
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-md border shrink-0 ${patient.payment_status === 'paid'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : 'bg-amber-50 text-amber-800 border-amber-200'
                            }`}
                        >
                          {patient.payment_status === 'paid' ? 'PAID' : 'FEE PENDING'}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-xs text-neutral-500">
                        <span className="truncate max-w-[240px]">
                          {patient.chief_complaint || 'General Consultation'}
                        </span>
                        {patient.appointment_time && (
                          <>
                            <span className="text-neutral-300">•</span>
                            <span className="font-mono text-neutral-500 flex items-center gap-1 shrink-0">
                              <Clock3 className="w-3.5 h-3.5 text-neutral-400" />
                              Original: {patient.appointment_time}
                            </span>
                          </>
                        )}
                        <span className="text-neutral-300">•</span>
                        <span
                          className={`font-semibold inline-flex items-center gap-1 shrink-0 ${isCancel
                            ? 'text-rose-600'
                            : currentStaged.action === 'rollover_same_time'
                              ? 'text-indigo-600'
                              : currentStaged.action === 'custom_time'
                                ? 'text-neutral-900'
                                : 'text-amber-700'
                            }`}
                        >
                          <ArrowRight className="w-3 h-3 text-neutral-400" />
                          {isCancel
                            ? 'Will be cancelled'
                            : `Tomorrow ${currentStaged.targetTime || '10:00 AM'}`}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center bg-neutral-100 p-1 rounded-xl border border-neutral-200/80 gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          updateItem(patient.id, {
                            action: 'rollover_morning',
                            targetTime: tomorrowSlots[0]?.time_label || '10:00 AM',
                          });
                          if (expandedCustomId === patient.id) setExpandedCustomId(null);
                        }}
                        className={`h-8 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 min-w-[96px] ${currentStaged.action === 'rollover_morning'
                          ? 'bg-neutral-900 text-white shadow-xs font-bold'
                          : 'text-neutral-600 hover:text-black hover:bg-neutral-200/70'
                          }`}
                        title="Move to first morning slot tomorrow"
                      >
                        <Sun className="w-3.5 h-3.5" />
                        <span>Morning</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          updateItem(patient.id, {
                            action: 'rollover_same_time',
                            targetTime: patient.appointment_time || '10:00 AM',
                          });
                          if (expandedCustomId === patient.id) setExpandedCustomId(null);
                        }}
                        className={`h-8 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 min-w-[104px] ${currentStaged.action === 'rollover_same_time'
                          ? 'bg-neutral-900 text-white shadow-xs font-bold'
                          : 'text-neutral-600 hover:text-black hover:bg-neutral-200/70'
                          }`}
                        title="Keep same time tomorrow"
                      >
                        <Clock3 className="w-3.5 h-3.5" />
                        <span>Same Time</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          updateItem(patient.id, {
                            action: 'custom_time',
                            targetTime: currentStaged.targetTime || tomorrowSlots[0]?.time_label || '10:00 AM',
                          });
                          setExpandedCustomId(isExpanded ? null : patient.id);
                        }}
                        className={`h-8 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 min-w-[92px] ${currentStaged.action === 'custom_time'
                          ? 'bg-neutral-900 text-white shadow-xs font-bold'
                          : 'text-neutral-600 hover:text-black hover:bg-neutral-200/70'
                          }`}
                        title="Pick custom slot window"
                      >
                        <Calendar className="w-3.5 h-3.5" />
                        <span>Custom</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          updateItem(patient.id, { action: 'cancel' });
                          if (expandedCustomId === patient.id) setExpandedCustomId(null);
                        }}
                        className={`h-8 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 min-w-[84px] ${currentStaged.action === 'cancel'
                          ? 'bg-rose-600 text-white shadow-xs font-bold'
                          : 'text-neutral-600 hover:text-rose-600 hover:bg-rose-50'
                          }`}
                        title="Cancel visit"
                      >
                        <X className="w-3.5 h-3.5" />
                        <span>Cancel</span>
                      </button>
                    </div>
                  </div>

                  {isCustom && isExpanded && (
                    <div className="border-t border-neutral-100 pt-3.5 bg-neutral-50/80 p-3.5 rounded-xl space-y-2.5 animate-in fade-in zoom-in-98 duration-100">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-neutral-700 flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                          Select Tomorrow Window for {patient.patient_name}
                        </span>
                        <span className="text-xs text-neutral-800 font-semibold font-mono bg-white px-2 py-0.5 rounded border border-neutral-200">
                          Selected: {currentStaged.targetTime || 'None'}
                        </span>
                      </div>

                      {tomorrowSlots.length === 0 ? (
                        <p className="text-xs text-neutral-500">
                          No pre-generated slot windows found for tomorrow. Defaulting to 10:00 AM.
                        </p>
                      ) : (
                        <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto pr-1">
                          {tomorrowSlots.map((s) => (
                            <button
                              key={s.time_label}
                              type="button"
                              onClick={() => {
                                updateItem(patient.id, { targetTime: s.time_label });
                              }}
                              className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold border transition-all cursor-pointer ${currentStaged.targetTime === s.time_label
                                ? 'bg-neutral-900 text-white border-neutral-900 shadow-xs'
                                : 'bg-white text-neutral-800 border-neutral-200 hover:border-neutral-400 hover:bg-neutral-50'
                                }`}
                            >
                              {s.time_label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {!isCancel && (
                    <label className="flex items-center gap-2 border-t border-neutral-100 pt-3 text-xs text-neutral-700">
                      <input
                        type="checkbox"
                        checked={currentStaged.patientConfirmed}
                        onChange={(event) => updateItem(patient.id, { patientConfirmed: event.target.checked })}
                        className="h-4 w-4 accent-neutral-900"
                      />
                      Patient or authorized representative confirmed the proposed time
                    </label>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="border-t border-neutral-200/90 px-6 py-4 bg-white flex items-center justify-between gap-4 flex-wrap">
          {batchMutation.isError && (
            <p role="alert" className="w-full text-xs font-semibold text-rose-700">
              A proposed time could not be saved. Refresh the available slots and review each patient before trying again.
            </p>
          )}
          <div className="flex items-center gap-3 text-xs">
            <span className="inline-flex items-center gap-1.5 font-bold px-3 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
              <RotateCcw className="w-3.5 h-3.5 text-amber-600" />
              <span>{rolloverCount} to Rollover</span>
            </span>
            <span className="inline-flex items-center gap-1.5 font-bold px-3 py-1 rounded-full bg-rose-50 text-rose-800 border border-rose-200">
              <Ban className="w-3.5 h-3.5 text-rose-500" />
              <span>{cancelCount} to Cancel</span>
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 hover:text-black transition-colors cursor-pointer"
            >
              Back
            </button>

            <button
              type="button"
              disabled={patients.length === 0 || batchMutation.isPending || Object.values(stagedMap).some((item) => item.action !== 'cancel' && !item.patientConfirmed)}
              onClick={handleExecuteReconciliation}
              className="px-5 py-2 rounded-xl bg-neutral-900 hover:bg-black text-white text-xs font-bold transition-all shadow-md flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {batchMutation.isPending ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Saving Changes...</span>
                </>
              ) : (
                <>
                  <span>Confirm</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
