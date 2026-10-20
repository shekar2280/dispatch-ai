'use client';

import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { AppointmentItem } from '../../types';

interface UrgentPatientModalProps {
  isOpen: boolean;
  patients: AppointmentItem[];
  isSubmitting: boolean;
  onClose: () => void;
  onOpenWalkIn: () => void;
  onConfirm: (appointmentId: string, reason: string) => Promise<void>;
}

export function UrgentPatientModal({ isOpen, patients, isSubmitting, onClose, onOpenWalkIn, onConfirm }: UrgentPatientModalProps) {
  const [appointmentId, setAppointmentId] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setAppointmentId('');
      setReason('');
      setError('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!appointmentId || reason.trim().length < 5 || isSubmitting) return;
    setError('');
    try {
      await onConfirm(appointmentId, reason.trim());
      onClose();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : err?.message || 'Unable to record urgency');
    }
  };

  return (
    <div role="presentation" className="fixed inset-0 z-[70] flex items-center justify-center bg-neutral-950/60 p-4 backdrop-blur-sm">
      <form role="dialog" aria-modal="true" aria-labelledby="urgent-patient-title" onSubmit={submit} className="w-full max-w-md overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-[#EAE6DF] bg-[#FBF9F5] px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="rounded-xl border border-amber-200 bg-amber-50 p-2 text-amber-800"><AlertTriangle className="h-4 w-4" /></span>
            <div>
              <h2 id="urgent-patient-title" className="text-base font-semibold tracking-tight text-neutral-950">Mark urgent patient</h2>
              <p className="mt-0.5 text-xs text-neutral-500">Staff confirmation for a checked-in patient</p>
            </div>
          </div>
          <button type="button" aria-label="Close urgent patient" onClick={onClose} disabled={isSubmitting} className="rounded-lg p-1.5 text-neutral-500 hover:bg-neutral-200/70 hover:text-neutral-950"><X className="h-4 w-4" /></button>
        </div>

        <div className="space-y-4 px-5 py-5">
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/70 px-3.5 py-3 text-xs leading-5 text-amber-950">
            Use this only when clinic staff confirm a patient needs to be seen sooner. The reason is saved in the visit history. It does not interrupt a consultation already in progress.
          </div>
          {patients.length ? (
            <>
              <label className="block text-[11px] font-semibold text-neutral-700">Checked-in patient <span className="text-rose-600">*</span>
                <select required aria-label="Checked-in urgent patient" value={appointmentId} onChange={event => setAppointmentId(event.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[#E8E4DC] bg-white px-3 text-xs font-medium text-neutral-900 outline-none focus:border-neutral-900">
                  <option value="">Select patient</option>
                  {patients.map(patient => <option key={patient.id} value={patient.id}>{patient.patient_name}{patient.display_token ? ` · ${patient.display_token}` : ''}</option>)}
                </select>
              </label>
              <label className="block text-[11px] font-semibold text-neutral-700">Staff-confirmed reason <span className="text-rose-600">*</span>
                <textarea required minLength={5} maxLength={500} aria-label="Urgency reason" value={reason} onChange={event => setReason(event.target.value)} placeholder="Describe why this patient needs earlier attention" className="mt-1.5 min-h-24 w-full resize-y rounded-xl border border-[#E8E4DC] bg-white p-3 text-xs font-medium text-neutral-900 outline-none placeholder:text-neutral-400 focus:border-neutral-900" />
              </label>
            </>
          ) : (
            <div className="rounded-xl border border-[#EAE6DF] bg-[#FBF9F5] p-4">
              <p className="text-xs font-semibold text-neutral-900">No checked-in patient to select</p>
              <p className="mt-1 text-xs text-neutral-500">Check in a new walk-in first, then confirm urgency from the waiting queue.</p>
              <button type="button" onClick={onOpenWalkIn} className="mt-3 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs font-semibold text-neutral-800 hover:bg-neutral-50">Open walk-in check-in</button>
            </div>
          )}
          {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-800">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-neutral-200 bg-[#FBF9F5] px-5 py-4">
          <button type="button" disabled={isSubmitting} onClick={onClose} className="rounded-xl border border-neutral-200 bg-white px-4 py-2.5 text-xs font-semibold text-neutral-700 hover:bg-neutral-50">Cancel</button>
          <button type="submit" disabled={!patients.length || !appointmentId || reason.trim().length < 5 || isSubmitting} className="rounded-xl bg-neutral-950 px-4 py-2.5 text-xs font-semibold text-white hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40">{isSubmitting ? 'Saving…' : 'Confirm urgency'}</button>
        </div>
      </form>
    </div>
  );
}
