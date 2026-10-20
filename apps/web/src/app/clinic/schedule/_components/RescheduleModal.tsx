'use client';

import React, { useState, useEffect } from 'react';
import { X, Calendar, Clock, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import { AppointmentItem } from '../../types';
import { useClinicSlotsQuery } from '../../_hooks/useClinicQueries';
import { useRescheduleAppointmentMutation } from '../../_hooks/useClinicMutations';
import { formatDateISO } from '../../utils';

interface RescheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  appointment: AppointmentItem | null;
  orgId?: string | null;
}

export function RescheduleModal({
  isOpen,
  onClose,
  appointment,
  orgId,
}: RescheduleModalProps) {
  const tomorrowStr = (() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return formatDateISO(d);
  })();

  const [selectedDate, setSelectedDate] = useState<string>(tomorrowStr);
  const [selectedTime, setSelectedTime] = useState<string>('');
  const [reason, setReason] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: slotsData, isFetching: isSlotsLoading, isError: slotsError, refetch: retrySlots } = useClinicSlotsQuery(orgId, isOpen ? selectedDate : null, appointment?.doctor_id);
  const rescheduleMutation = useRescheduleAppointmentMutation(orgId);

  useEffect(() => {
    if (isOpen) {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      setSelectedDate(formatDateISO(d));
      setSelectedTime('');
      setReason('');
      setErrorMessage(null);
    }
  }, [isOpen]);

  if (!isOpen || !appointment) return null;

  const todayStr = formatDateISO(new Date());
  const availableSlots = (slotsData?.slots || []).filter(
    (s) => s.is_available && s.status_type === 'AVAILABLE'
  );

  const handleConfirm = async () => {
    if (!selectedTime || isSlotsLoading || slotsError || !availableSlots.some(slot => slot.time_label === selectedTime)) {
      setErrorMessage('Please select a time slot.');
      return;
    }
    setErrorMessage(null);
    try {
      await rescheduleMutation.mutateAsync({
        appointmentId: appointment.id,
        new_date: selectedDate,
        new_time: selectedTime,
        reason: reason.trim() || undefined,
      });
      onClose();
    } catch (err: any) {
      const detail = err?.data?.detail ?? err?.response?.data?.detail;
      const msg = typeof detail === 'object' && detail?.message ? detail.message : detail || 'Failed to reschedule appointment.';
      setErrorMessage(msg);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-neutral-950/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white border border-neutral-200/90 rounded-2xl w-full max-w-lg shadow-2xl flex flex-col overflow-hidden">
        <div className="px-6 py-4.5 border-b border-neutral-100 flex items-center justify-between bg-neutral-50/50">
          <div>
            <h2 className="text-base font-semibold text-neutral-900 tracking-tight">Reschedule appointment</h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              Moving appointment for <span className="font-semibold text-neutral-800">{appointment.patient_name}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto max-h-[70vh]">
          {errorMessage && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="p-3.5 rounded-xl bg-neutral-50 border border-neutral-200/80 flex items-center justify-between text-xs">
            <span className="text-neutral-500">Current Slot:</span>
            <span className="font-semibold text-neutral-900">
              {appointment.appointment_date || 'Today'} at {appointment.appointment_time || 'Walk-in Queue'}
            </span>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-neutral-800 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-neutral-500" /> New date
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => { setSelectedDate(todayStr); setSelectedTime(''); }}
                className={`py-2 px-3 rounded-xl border text-xs font-medium transition-all ${
                  selectedDate === todayStr
                    ? 'border-neutral-900 bg-neutral-900 text-white shadow-xs'
                    : 'border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50'
                }`}
              >
                Today
              </button>
              <button
                type="button"
                onClick={() => { setSelectedDate(tomorrowStr); setSelectedTime(''); }}
                className={`py-2 px-3 rounded-xl border text-xs font-medium transition-all ${
                  selectedDate === tomorrowStr
                    ? 'border-neutral-900 bg-neutral-900 text-white shadow-xs'
                    : 'border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50'
                }`}
              >
                Tomorrow
              </button>
              <input
                type="date"
                min={todayStr}
                value={selectedDate}
                onChange={(e) => { setSelectedDate(e.target.value); setSelectedTime(''); }}
                className="py-2 px-2.5 rounded-xl border border-neutral-200 text-xs font-medium text-neutral-800 bg-white focus:outline-none focus:border-neutral-900"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-neutral-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-neutral-500" /> Available times
              </span>
              <span className="text-[11px] font-normal text-neutral-500">
                {availableSlots.length} open
              </span>
            </label>

            {isSlotsLoading ? (
              <div className="py-8 flex items-center justify-center text-xs text-neutral-400 gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-neutral-500" />
                Loading available times…
              </div>
            ) : slotsError ? (
              <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">Unable to load available times. <button type="button" onClick={() => retrySlots()} className="underline">Retry</button></div>
            ) : availableSlots.length === 0 ? (
              <div className="py-6 text-center text-xs text-neutral-500 bg-neutral-50 border border-neutral-200/80 rounded-xl">
                No appointment capacity remaining on {selectedDate}. Choose another date.
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-48 overflow-y-auto pr-1">
                {availableSlots.map((slot) => (
                  <button
                    key={slot.time_label}
                    type="button"
                    onClick={() => setSelectedTime(slot.time_label)}
                    className={`py-2 px-2 rounded-xl text-xs font-semibold transition-all border ${
                      selectedTime === slot.time_label
                        ? 'border-neutral-900 bg-neutral-900 text-white shadow-xs scale-[0.98]'
                        : 'border-neutral-200 bg-white text-neutral-800 hover:border-neutral-300 hover:bg-neutral-50'
                    }`}
                  >
                    {slot.time_label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-neutral-700">Reschedule Note (Optional)</label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Patient requested morning slot"
              className="w-full px-3.5 py-2.5 rounded-xl border border-neutral-200 bg-white text-xs text-neutral-900 placeholder-neutral-400 focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900/10"
            />
          </div>
        </div>

        <div className="px-6 py-4 border-t border-neutral-100 flex items-center justify-end gap-2.5 bg-neutral-50/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-neutral-600 hover:bg-neutral-100 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!selectedTime || isSlotsLoading || slotsError || rescheduleMutation.isPending || !availableSlots.some(slot => slot.time_label === selectedTime)}
            className="px-5 py-2 rounded-xl text-xs font-semibold bg-neutral-900 hover:bg-neutral-850 text-white flex items-center gap-1.5 transition-all shadow-xs disabled:opacity-50 disabled:pointer-events-none"
          >
            {rescheduleMutation.isPending ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Rescheduling...
              </>
            ) : (
              <>
                Reschedule
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
