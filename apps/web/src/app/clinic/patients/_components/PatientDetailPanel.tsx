'use client';

import React, { useEffect, useRef } from 'react';
import { Activity, ArrowUpRight, CalendarDays, Check, FileText, Loader2, Phone, Plus, UserRound, X } from 'lucide-react';
import { PatientRecordItem } from '../../types';

type PatientWithUI = PatientRecordItem & { temperature?: string; heart_rate?: string; blood_pressure?: string };
type Tab = 'Overview' | 'History' | 'Notes';

interface PatientDetailPanelProps {
  patient: PatientWithUI;
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  onClose: () => void;
  doctorNoteInput: string;
  onDoctorNoteChange: (value: string) => void;
  onSaveNote: () => void;
  isSavingNote: boolean;
  noteSavedSuccess: boolean;
  noteError?: string;
  canEditNotes: boolean;
}

function displayDate(value?: string | null, withTime = false) {
  if (!value) return 'Date not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}) });
}

const visitLabels: Record<string, string> = { scheduled: 'Scheduled', arrived: 'Checked in', in_progress: 'In consultation', completed: 'Completed', cancelled: 'Cancelled', no_show: 'Did not attend' };

export function PatientDetailPanel({ patient, activeTab, onTabChange, onClose, doctorNoteInput, onDoctorNoteChange, onSaveNote, isSavingNote, noteSavedSuccess, noteError, canEditNotes }: PatientDetailPanelProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
  }, []);
  const entries = patient.note_entries || [];
  const legacyNotes = (patient.notes || []).filter((note) => !entries.some((entry) => entry.text === note));
  const visits = patient.visit_history || [];
  const focusClass = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2';

  return (
    <dialog ref={dialogRef} aria-labelledby="patient-record-title" onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right) onClose(); } }}
      className="fixed inset-y-0 left-auto right-0 m-0 h-dvh max-h-none w-full max-w-[620px] border-0 border-l border-neutral-200 bg-white p-0 text-neutral-900 shadow-[-12px_0_48px_rgba(13,38,34,0.12)] backdrop:bg-neutral-950/20 backdrop:backdrop-blur-[1px]">
      <div className="flex h-full min-h-0 flex-col">
        <header className="shrink-0 border-b border-neutral-100 px-6 pb-0 pt-4 sm:px-8">
          <div className="mb-6 flex items-center justify-between">
            <span className="flex items-center gap-2 text-xs text-neutral-500"><FileText className="h-3.5 w-3.5" />Patient record</span>
            <button autoFocus type="button" onClick={onClose} aria-label="Close patient record" className={`flex h-9 w-9 items-center justify-center rounded-lg text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 ${focusClass}`}><X className="h-4 w-4" /></button>
          </div>
          <div className="mb-5 flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#E3EBE0] text-sm font-semibold text-[#1E6B56]">{patient.name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('')}</span>
            <div className="min-w-0"><h2 id="patient-record-title" className="break-words text-2xl font-semibold tracking-tight">{patient.name}</h2><p className="mt-1 text-xs text-neutral-500">{patient.age_gender} <span className="mx-1.5 text-neutral-300">·</span> {patient.total_visits} {patient.total_visits === 1 ? 'visit' : 'visits'} on record</p></div>
          </div>
          <div role="tablist" aria-label="Patient record sections" className="flex gap-6">
            {(['Overview', 'History', 'Notes'] as const).map((tab) => <button key={tab} id={`patient-tab-${tab}`} type="button" role="tab" aria-selected={activeTab === tab} aria-controls="patient-record-content" onClick={() => onTabChange(tab)} className={`min-h-11 border-b-2 text-sm transition ${focusClass} ${activeTab === tab ? 'border-[#1E6B56] font-medium text-[#1E6B56]' : 'border-transparent text-neutral-500 hover:text-neutral-900'}`}>{tab}{tab === 'Notes' && canEditNotes && entries.length + legacyNotes.length > 0 && <span className="ml-1.5 text-[10px] text-neutral-400">{entries.length + legacyNotes.length}</span>}</button>)}
          </div>
        </header>

        <div id="patient-record-content" role="tabpanel" aria-labelledby={`patient-tab-${activeTab}`} className="flex min-h-0 flex-1 flex-col">
          {activeTab === 'Overview' && <div className="flex-1 space-y-7 overflow-y-auto px-6 py-6 sm:px-8">
            <section><h3 className="mb-4 text-xs font-medium uppercase tracking-wider text-neutral-400">Patient details</h3>
              <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-4 gap-y-4 text-sm">
                <dt className="text-neutral-500">Contact</dt><dd><a href={`tel:${patient.phone}`} className={`inline-flex items-center gap-2 rounded text-neutral-800 hover:text-[#1E6B56] ${focusClass}`}><Phone className="h-3.5 w-3.5 text-neutral-400" />{patient.phone}<ArrowUpRight className="h-3 w-3 text-neutral-400" /></a></dd>
                <dt className="text-neutral-500">Date of birth</dt><dd>{patient.dob ? displayDate(patient.dob) : 'Not recorded'}</dd>
                <dt className="text-neutral-500">Blood group</dt><dd>{patient.blood_group || 'Not recorded'}</dd>
                <dt className="text-neutral-500">Latest visit</dt><dd>{patient.last_visit || 'No visits yet'}</dd>
              </dl>
              <p className="mt-5 rounded-lg bg-neutral-50 px-3 py-2 text-xs leading-relaxed text-neutral-500">A contact number may be shared. This record belongs to {patient.name}.</p>
            </section>
            {canEditNotes && <section className="border-t border-neutral-100 pt-6"><h3 className="mb-4 flex items-center gap-2 text-sm font-medium"><Activity className="h-4 w-4 text-neutral-400" />Clinical overview</h3>
              <dl className="space-y-4 text-sm">{[['Latest diagnosis', patient.recent_diagnosis], ['Allergies', patient.allergies], ['Ongoing conditions', patient.chronic_conditions]].map(([label, value]) => <div key={label}><dt className="mb-1 text-xs text-neutral-500">{label}</dt><dd className="whitespace-pre-wrap leading-relaxed text-neutral-800">{value || 'Not recorded'}</dd></div>)}</dl>
            </section>}
            {canEditNotes && <section className="border-t border-neutral-100 pt-6"><h3 className="text-sm font-medium">Vitals</h3><p className="mt-2 text-xs leading-relaxed text-neutral-500">Vitals are recorded during a consultation.</p>
              {(patient.temperature || patient.blood_pressure || patient.heart_rate) && <p className="mt-3 text-sm">{[patient.temperature && `Temperature: ${patient.temperature}`, patient.blood_pressure && `BP: ${patient.blood_pressure}`, patient.heart_rate && `Heart rate: ${patient.heart_rate}`].filter(Boolean).join(' · ')}</p>}
            </section>}
          </div>}

          {activeTab === 'History' && <div className="flex-1 overflow-y-auto px-6 py-6 sm:px-8">
            <h3 className="text-sm font-medium">Visit history</h3><p className="mb-5 mt-1 text-xs text-neutral-500">Appointments and notes recorded for each visit.</p>
            {visits.length === 0 ? <div className="rounded-xl border border-dashed border-neutral-200 px-5 py-10 text-center"><CalendarDays className="mx-auto h-6 w-6 text-neutral-300" /><p className="mt-3 text-sm text-neutral-500">No visit history available.</p></div> : <div className="space-y-5">{visits.map((visit) => <article key={visit.id} className="border-l-2 border-[#E3EBE0] pl-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-medium">{displayDate(visit.date, true)}</h4><span className="rounded-md bg-neutral-100 px-2 py-1 text-[11px] text-neutral-600">{visitLabels[visit.status] || 'Visit'}</span></div>{canEditNotes && <><p className="mt-2 text-xs text-neutral-500">{visit.diagnosis || 'No diagnosis recorded'}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-neutral-700">{visit.doctor_notes || 'No consultation note recorded.'}</p></>}</article>)}</div>}
          </div>}

          {activeTab === 'Notes' && <>
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-6 sm:px-8">
              <div><h3 className="text-sm font-medium">Patient notes</h3><p className="mt-1 text-xs text-neutral-500">General care notes. Visit-specific notes stay with their consultation.</p></div>
              {!canEditNotes ? <p className="rounded-lg bg-neutral-50 p-4 text-sm text-neutral-500">Clinical notes are available to clinicians.</p> : entries.length + legacyNotes.length === 0 ? <div className="py-8 text-center"><FileText className="mx-auto h-6 w-6 text-neutral-300" /><p className="mt-3 text-sm text-neutral-500">No notes yet.</p><p className="mt-1 text-xs text-neutral-400">Add the first care note below.</p></div> : <>
                {entries.map((entry) => <article key={entry.id} className="border-b border-neutral-100 pb-5"><div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"><span className="font-medium text-neutral-700">{entry.author_name || 'Clinician'}</span><span className="text-neutral-400">{displayDate(entry.created_at, true)}</span></div><p className="whitespace-pre-wrap break-words text-sm leading-7 text-neutral-800">{entry.text}</p></article>)}
                {legacyNotes.map((note, index) => <article key={`earlier-${index}`} className="border-b border-neutral-100 pb-5"><p className="mb-2 text-xs text-neutral-400">Earlier note · Date not recorded</p><p className="whitespace-pre-wrap break-words text-sm leading-7 text-neutral-800">{note}</p></article>)}
              </>}
            </div>
            {canEditNotes && <div className="shrink-0 border-t border-neutral-100 bg-white px-6 py-4 sm:px-8">
              <label htmlFor="patient-note-draft" className="mb-2 block text-xs font-medium text-neutral-600">Add a note for {patient.name}</label>
              <textarea id="patient-note-draft" rows={3} maxLength={5000} value={doctorNoteInput} onChange={(event) => onDoctorNoteChange(event.target.value)} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && doctorNoteInput.trim() && !isSavingNote) { event.preventDefault(); onSaveNote(); } }} placeholder="Write observations or a care plan…" className="w-full resize-y rounded-xl border border-neutral-200 bg-neutral-50/50 px-3 py-3 text-sm leading-relaxed outline-none placeholder:text-neutral-400 focus:border-[#1E6B56] focus:ring-2 focus:ring-[#1E6B56]/10" />
              {noteError && <p role="alert" className="mt-2 text-xs text-rose-700">{noteError}</p>}
              <div className="mt-3 flex items-center justify-between gap-3"><span role="status" className="text-xs text-neutral-400">{noteSavedSuccess ? <span className="flex items-center gap-1 text-[#1E6B56]"><Check className="h-3 w-3" />Note saved</span> : doctorNoteInput ? `${doctorNoteInput.length.toLocaleString()} / 5,000 · Unsaved draft` : 'Notes are saved to this patient’s record.'}</span>
                <button type="button" onClick={onSaveNote} disabled={!doctorNoteInput.trim() || isSavingNote} className={`inline-flex min-h-10 shrink-0 items-center gap-2 rounded-lg bg-[#0D2622] px-4 text-xs font-medium text-white hover:bg-[#1E6B56] disabled:cursor-not-allowed disabled:opacity-40 ${focusClass}`}>{isSavingNote ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}{isSavingNote ? 'Saving…' : 'Save note'}</button></div>
            </div>}
          </>}
        </div>
      </div>
    </dialog>
  );
}
