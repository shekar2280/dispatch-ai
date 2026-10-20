'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Check, ArrowRight, CalendarDays, UserRound, X } from 'lucide-react';
import { useClinicStore } from '../store';
import { useAddWalkInMutation, useBookAppointmentMutation } from '../_hooks/useClinicMutations';
import { useArrivalOptions, usePatientLookup, useClinicDoctors, useClinicTimezone } from '../_hooks/useClinicQueries';
import { ClinicCalendarPopover } from './ClinicCalendarPopover';
import PatientIntakeFields, { IntakeValues, validIntake } from './PatientIntakeFields';

const emptyIntake = (): IntakeValues => ({ name: '', phone: '', dob: '', age: '', ageUnit: 'years' });
const fieldClass = 'mt-2 h-10 w-full rounded-lg border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] px-3 text-xs text-[#0D2622] placeholder:text-[rgba(13,38,34,0.4)] outline-none focus:border-[#0D2622] focus:ring-1 focus:ring-[#0D2622]';
const labelClass = 'text-[11px] font-semibold text-[#0D2622]';

export function QuickBookingModal() {
  const store = useClinicStore();
  const isOpen = store.isBookingModalOpen;
  const timezone = useClinicTimezone(store.orgId);
  const today = timezone ? new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()) : '';
  const tomorrow = timezone ? new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(Date.now() + 86_400_000)) : '';
  const [value, setValue] = useState<IntakeValues>(emptyIntake);
  const [patientId, setPatientId] = useState<string>();
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [complaint, setComplaint] = useState('');
  const [error, setError] = useState('');
  const [calendarOpen, setCalendarOpen] = useState(false);
  const isTodayVisit = date === today;
  const walkin = store.bookingModalType === 'Walk-in' && isTodayVisit;
  const slotBooking = !!store.bookingInitialDate && !!store.bookingInitialTime;
  const { data: doctors = [], isPending: doctorsLoading, isError: doctorsError, refetch: retryDoctors } = useClinicDoctors(store.orgId);
  const doctorId = doctors[0]?.id || '';
  const { data: matches = [] } = usePatientLookup(store.orgId, value.phone, value.name, isOpen);
  const { data: slots, isFetching: slotsLoading, isError: slotsError, refetch: retrySlots } = useArrivalOptions(store.orgId, date, doctorId, !walkin && isOpen);
  const add = useAddWalkInMutation(store.orgId);
  const book = useBookAppointmentMutation(store.orgId);
  const pending = add.isPending || book.isPending;

  const prevOpenRef = useRef(false);

  useEffect(() => {
    const justOpened = isOpen && !prevOpenRef.current;
    prevOpenRef.current = isOpen;

    if (!justOpened) return;

    const followUp = store.followUpVisit;
    setValue(followUp ? { ...emptyIntake(), name: followUp.patient_name, phone: followUp.patient_phone } : emptyIntake());
    setPatientId(followUp?.patient_id);
    setDate(store.bookingInitialDate || (store.bookingModalType === 'Walk-in' ? today : ''));
    setTime(store.bookingInitialTime || '');
    setComplaint('');
    setCalendarOpen(false);
    setError('');
  }, [isOpen, store.bookingInitialDate, store.bookingInitialTime, store.bookingModalType, store.followUpVisit, today]);


  if (!isOpen) return null;

  const selectMode = (mode: 'Pre-booked' | 'Walk-in') => {
    if (pending) return;
    if (mode === 'Walk-in' && store.followUpVisit) store.setFollowUpVisit(null);
    store.setBookingModalType(mode);
    setCalendarOpen(false);
    setDate(mode === 'Walk-in' ? today : '');
    setTime('');
    setError('');
  };

  const selectDate = (nextDate: string) => {
    setCalendarOpen(false);
    setDate(nextDate);
    setTime('');
    if (nextDate !== today) store.setBookingModalType('Pre-booked');
    setError('');
  };

  const selectedDateLabel = date ? new Date(`${date}T12:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }) : 'Choose a date';

  const canSubmit = !pending && !!timezone && !!date && !!doctorId && !doctorsError && validIntake(value, walkin) && (walkin || (!slotsLoading && !slotsError && !!time && (slots?.available_slots ?? []).includes(time)));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setError('');
    const identity = {
      patient_name: value.name.trim(),
      patient_phone: value.phone.trim(),
      patient_id: patientId,
      doctor_id: doctorId,
      chief_complaint: complaint.trim() || undefined,
      dob: value.dob || undefined,
      reported_age: !value.dob && value.age.trim() ? Number(value.age) : undefined,
      age_unit: value.ageUnit,
      ...(walkin ? { gender: value.gender || undefined, blood_group: value.bloodGroup || undefined, address: value.address?.trim() || undefined } : {}),
    };
    try {
      if (walkin) {
        await add.mutateAsync({ ...identity, appointment_date: today, is_walkin: true, is_arrived: true });
      } else {
        await book.mutateAsync({ ...identity, appointment_date: date, appointment_time: time, previous_visit_id: store.followUpVisit?.id });
      }
      store.setBookingModalOpen(false);
    } catch (err: any) {
      const detail = err?.data?.detail ?? err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || err?.message || 'Unable to save visit');
    }
  };

  const availableSlots = slots?.available_slots ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0D2622]/60 p-3 backdrop-blur-sm sm:p-6">
      <form role="dialog" aria-modal="true" aria-labelledby="booking-title" onSubmit={submit} className="flex max-h-[calc(100dvh-2rem)] w-full max-w-lg flex-col rounded-2xl bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] shadow-2xl overflow-hidden">
        <header className="flex items-center gap-3 px-5 pt-5 sm:px-6 sm:pt-6 bg-[#F1F4EE]/50 pb-3 border-b border-[rgba(13,38,34,0.08)]">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#E3EBE0] text-[#0D2622] border border-[rgba(13,38,34,0.12)]">{walkin ? <UserRound className="h-5 w-5 text-[#1E6B56]" /> : <CalendarDays className="h-5 w-5 text-[#1E6B56]" />}</div>
          <h2 id="booking-title" className="flex-1 text-base font-bold tracking-tight text-[#0D2622]">{store.followUpVisit ? 'Book report review' : slotBooking ? 'Book appointment' : walkin ? 'Add walk-in' : 'Book a visit'}</h2>
          <button type="button" disabled={pending} aria-label="Close booking" onClick={() => store.setBookingModalOpen(false)} className="rounded-lg p-2 text-[rgba(13,38,34,0.5)] hover:bg-[#E3EBE0] hover:text-[#0D2622]"><X className="h-4 w-4" /></button>
        </header>
        {!slotBooking && !store.followUpVisit && <nav className="flex gap-6 border-b border-[rgba(13,38,34,0.1)] px-5 sm:px-6 pt-3 bg-[#F1F4EE]/30" aria-label="Visit type">
          {(['Walk-in', 'Pre-booked'] as const).map(mode => <button key={mode} type="button" disabled={pending} onClick={() => selectMode(mode)} aria-pressed={mode === 'Walk-in' ? walkin : !walkin} className={`border-b-2 pb-3 text-xs font-semibold transition-colors ${(mode === 'Walk-in' ? walkin : !walkin) ? 'border-[#0D2622] text-[#0D2622]' : 'border-transparent text-[rgba(13,38,34,0.5)] hover:text-[#0D2622]'}`}>{mode === 'Walk-in' ? 'Walk-in' : 'Future appointment'}</button>)}
        </nav>}
        <div className={`min-h-0 px-5 py-5 sm:px-6 sm:py-5 ${calendarOpen ? 'overflow-visible' : 'overflow-y-auto'}`}>
          {!walkin && !slotBooking && <section className="mb-4 space-y-3 border-b border-[rgba(13,38,34,0.08)] pb-4">
            <div className="relative" role="group" aria-label="Visit date picker">
              <span className={labelClass}>Visit date</span>
              <button type="button" disabled={!timezone || pending} aria-label="Visit date" aria-expanded={calendarOpen} onClick={() => setCalendarOpen(!calendarOpen)} className={`${fieldClass} flex items-center justify-between text-left`}><span>{selectedDateLabel}</span><CalendarDays className="h-4 w-4 text-[rgba(13,38,34,0.5)]" /></button>
              {calendarOpen && <ClinicCalendarPopover selectedDate={date || null} minDate={tomorrow} onSelectDate={selectDate} onClose={() => setCalendarOpen(false)} align="left" />}
            </div>
            <div>
              <div className="mb-3 flex items-center justify-between text-[11px]"><span className="font-semibold text-[#0D2622]">Available times</span><span className="text-[rgba(13,38,34,0.6)]">{date ? selectedDateLabel : 'Select a date'}</span></div>
              <div className="grid max-h-28 grid-cols-4 gap-1.5 overflow-y-auto" role="radiogroup" aria-label="Arrival time">
                {availableSlots.map(slot => <button type="button" role="radio" aria-checked={time === slot} key={slot} onClick={() => setTime(slot)} className={`h-8 rounded-lg border text-xs font-semibold transition-colors ${time === slot ? 'border-[#0D2622] bg-[#0D2622] text-[#F1F4EE]' : 'border-[rgba(13,38,34,0.14)] bg-[#FFFFFF] text-[#0D2622] hover:border-[#0D2622]'}`}>{slot}</button>)}
              </div>
              {slotsLoading && <div role="status" className="py-2 text-xs text-[rgba(13,38,34,0.65)]">Checking availability…</div>}
              {!date && <div className="flex items-center gap-2 py-2 text-xs text-[rgba(13,38,34,0.5)]"><CalendarDays className="h-4 w-4" />Choose a date to view times</div>}
              {date && slotsError && <div role="alert" className="py-3 text-xs text-rose-700">Unable to load times. <button type="button" onClick={() => retrySlots()} className="underline">Retry</button></div>}
              {date && doctorId && !slotsLoading && !slotsError && slots && !availableSlots.length && <div className="py-2 text-xs text-[rgba(13,38,34,0.65)]">{slots.reason || 'No times available. Choose another date.'}</div>}
            </div>
          </section>}
          <section className="space-y-4">
            <div className="flex items-center justify-between border-b border-[rgba(13,38,34,0.08)] pb-3">
              <span className="text-xs font-bold text-[#0D2622]">Patient details</span>
              {(walkin || slotBooking) && <span className="rounded-md bg-[#E3EBE0] px-2.5 py-1 text-[11px] font-semibold text-[#0D2622] border border-[rgba(13,38,34,0.1)]">{walkin ? 'Today · walk-in' : `${selectedDateLabel} · ${time}`}</span>}
            </div>
            {walkin ? <PatientIntakeFields compact value={value} requireAge onChange={next => { setValue(next); if (next.name !== value.name || next.phone !== value.phone) setPatientId(undefined); }} /> : <div className="grid gap-4 sm:grid-cols-2">
              <label className={labelClass}>Patient name<input aria-label="Patient name" required autoComplete="name" placeholder="Full name" value={value.name} onChange={e => { setValue({ ...value, name: e.target.value }); setPatientId(undefined); }} className={fieldClass} /></label>
              <label className={labelClass}>Phone number<input aria-label="Contact number" required type="tel" autoComplete="tel" placeholder="Mobile number" value={value.phone} onChange={e => { setValue({ ...value, phone: e.target.value }); setPatientId(undefined); }} className={fieldClass} /></label>
            </div>}
            {matches.length > 0 && (
              <div className="rounded-xl border border-[rgba(13,38,34,0.14)] bg-[#F1F4EE]/60 p-2.5">
                <p className="mb-2 text-[11px] font-semibold text-[#0D2622]">Existing patient? Tap to select.</p>
                <div className="space-y-1.5">
                  {matches.slice(0, 3).map(patient => (
                    <button type="button" key={patient.id} onClick={() => { setPatientId(patient.id); setValue({ ...value, name: patient.name, phone: patient.phone, dob: patient.dob || '', age: patient.reported_age == null ? '' : String(patient.reported_age), ageUnit: patient.age_unit || 'years', gender: patient.gender?.toLowerCase() || '', bloodGroup: patient.blood_group || '', address: patient.address || '' }); }} className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs transition-colors ${patientId === patient.id ? 'border-[#0D2622] bg-[#FFFFFF] text-[#0D2622] font-semibold shadow-2xs' : 'border-[rgba(13,38,34,0.14)] bg-[#FFFFFF] text-[rgba(13,38,34,0.8)] hover:border-[#0D2622]'}`}>
                      <span>{patient.name} <span className="text-[rgba(13,38,34,0.5)]">· {patient.phone}</span></span>
                      {patientId === patient.id && <Check className="h-3.5 w-3.5 text-[#1E6B56]" />}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <label className={`block ${labelClass}`}>Reason for visit <span className="font-normal text-[rgba(13,38,34,0.5)]">(optional)</span>
              <input value={complaint} onChange={event => setComplaint(event.target.value)} placeholder="Brief note for the doctor" className={fieldClass} />
            </label>

          </section>
          {doctorsLoading && <div role="status" className="mt-3 text-xs text-[rgba(13,38,34,0.65)]">Loading clinic details…</div>}
          {doctorsError && <div role="alert" className="mt-3 text-xs text-rose-700">Unable to load clinic details. <button type="button" onClick={() => retryDoctors()} className="underline">Retry</button></div>}
          {!doctorsLoading && !doctorsError && !doctorId && <div role="alert" className="mt-3 text-xs text-rose-700">No active doctor is configured for this clinic.</div>}
          {error && <div role="alert" className="mt-3 rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-700">{error}</div>}
        </div>
        <footer className="flex items-center justify-between gap-3 border-t border-[rgba(13,38,34,0.08)] bg-[#F1F4EE]/50 px-5 py-4 sm:px-6">
          <button type="button" disabled={pending} onClick={() => store.setBookingModalOpen(false)} className="text-xs font-semibold text-[rgba(13,38,34,0.6)] hover:text-[#0D2622]">Cancel</button>
          <button type="submit" disabled={!canSubmit} className="flex h-10 items-center gap-3 rounded-xl bg-[#0D2622] px-5 text-xs font-semibold text-[#F1F4EE] hover:bg-[#143530] disabled:cursor-not-allowed disabled:opacity-35 cursor-pointer shadow-xs transition-colors">{pending ? 'Saving…' : walkin ? 'Check in patient' : 'Book appointment'}<ArrowRight className="h-3.5 w-3.5 text-[#F4B63A]" /></button>
        </footer>
      </form>
    </div>
  );
}
