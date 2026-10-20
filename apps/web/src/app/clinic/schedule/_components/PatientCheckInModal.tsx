 'use client';
import React, {useEffect, useState} from 'react';
import {useClinicDoctors} from '../../_hooks/useClinicQueries';
import {useClinicStore} from '../../store';
import {AppointmentItem} from '../../types';
import PatientIntakeFields, {IntakeValues, validIntake} from '../../_components/PatientIntakeFields';

interface CheckInPayload {
  appointmentId: string;
  doctor_id?: string;
  patient_name: string;
  patient_phone: string;
  gender?: string;
  blood_group?: string;
  address?: string;
  dob?: string;
  reported_age?: number;
  age_unit: 'years' | 'months';
  chief_complaint?: string;
}
export default function PatientCheckInModal({isOpen, appointment, onClose, onConfirm, isSubmitting}: {
  isOpen: boolean; appointment: AppointmentItem | null; onClose: () => void;
  onConfirm: (payload: CheckInPayload) => Promise<void>; isSubmitting?: boolean;
}) {
  const [value, setValue] = useState<IntakeValues>({name: '', phone: '', dob: '', age: '', ageUnit: 'years'});
  const orgId = useClinicStore(s => s.orgId);
  const {data: doctors = [], isPending: doctorsLoading, isError: doctorsError, refetch: retryDoctors} = useClinicDoctors(orgId);
  const [complaint, setComplaint] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!appointment) return;
    setValue({name: appointment.patient_name, phone: appointment.patient_phone, dob: appointment.dob || '', age: appointment.reported_age == null ? '' : String(appointment.reported_age), ageUnit: appointment.age_unit || 'years', gender: appointment.gender?.toLowerCase() || '', bloodGroup: appointment.blood_group || '', address: appointment.address || ''});
    setComplaint(appointment.chief_complaint || ''); setError('');
  }, [appointment, isOpen]);
  if (!isOpen || !appointment) return null;
  const doctorId = appointment.doctor_id || doctors[0]?.id || '';
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"><form className="max-h-[calc(100dvh-2rem)] w-full max-w-lg space-y-5 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl" onSubmit={async e => {
    e.preventDefault(); if (!doctorId || !validIntake(value) || isSubmitting) return;
    try {await onConfirm({appointmentId: appointment.id, doctor_id: doctorId || undefined, patient_name: value.name.trim(), patient_phone: value.phone.trim(), dob: value.dob || undefined, reported_age: value.dob ? undefined : Number(value.age), age_unit: value.ageUnit, gender: value.gender || undefined, blood_group: value.bloodGroup || undefined, address: value.address?.trim() || undefined, chief_complaint: complaint}); onClose();}
    catch (err: any) {const detail = err?.data?.detail ?? err?.response?.data?.detail; setError(typeof detail === 'string' ? detail : detail?.message || err?.message || 'Check-in failed');}
  }}>
    <h2 className="text-base font-semibold tracking-tight text-neutral-950">Verify patient and check in</h2>
    <p className="text-xs text-neutral-500">Confirm the patient is here. Their queue position begins at check-in. Billing follows consultation.</p>
    <PatientIntakeFields value={value} onChange={setValue} />
    <label className="block text-[11px] font-semibold text-neutral-700">Reason for visit (optional)<input className="mt-1 w-full rounded-xl border border-[#E8E4DC] bg-white px-3 py-2.5 text-xs font-medium outline-none focus:border-neutral-900" value={complaint} onChange={e => setComplaint(e.target.value)} /></label>
    {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
    {!doctorId && doctorsLoading && <p role="status" className="text-xs text-neutral-500">Loading clinic details…</p>}
    {!doctorId && doctorsError && <p role="alert" className="text-xs text-red-700">Unable to load clinic details. <button type="button" onClick={() => retryDoctors()} className="underline">Retry</button></p>}
    {!doctorId && !doctorsLoading && !doctorsError && <p role="alert" className="text-xs text-red-700">No active doctor is configured for this clinic. Check the clinic’s staff settings.</p>}
    <div className="flex justify-end gap-3"><button type="button" disabled={isSubmitting} onClick={onClose} className="rounded-xl border border-neutral-200 px-4 py-2.5 text-xs font-semibold">Cancel</button><button disabled={isSubmitting || !doctorId || !validIntake(value)} className="rounded-xl bg-neutral-950 px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-40">{isSubmitting ? 'Checking in…' : 'Check in and join queue'}</button></div>
  </form></div>;
}
