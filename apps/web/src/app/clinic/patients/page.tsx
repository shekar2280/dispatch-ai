'use client';

import React, { useMemo, useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { Plus, ChevronLeft, ChevronRight, AlertCircle, RefreshCw } from 'lucide-react';
import { useClinicStore } from '../store';
import { useClinicPatientsQuery } from '../_hooks/useClinicQueries';
import { useSavePatientEhrNoteMutation } from '../_hooks/useClinicMutations';
import { PatientsDirectorySkeleton, PatientsPageSkeleton } from '../_components/ClinicSkeletons';
import { PatientList } from './_components/PatientList';
import { PatientDetailPanel } from './_components/PatientDetailPanel';

function PatientsContent() {
  const orgId = useClinicStore((state) => state.orgId);
  const activeRole = useClinicStore((state) => state.activeRole);
  const openBooking = useClinicStore((state) => state.setBookingModalOpen);
  const saveNote = useSavePatientEhrNoteMutation(orgId);
  const params = useSearchParams();
  const queryId = params.get('id');
  const queryPhone = params.get('phone');
  const queryName = params.get('name');
  const [search, setSearch] = useState(queryPhone || queryName || '');
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(queryId);
  const [activeTab, setActiveTab] = useState<'Overview' | 'History' | 'Notes'>('Overview');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [noteErrors, setNoteErrors] = useState<Record<string, string>>({});
  const [savedPatientId, setSavedPatientId] = useState<string | null>(null);
  const [savingNotes, setSavingNotes] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    setSelectedId(queryId);
    setSearch(queryPhone || queryName || '');
    setActiveTab('Overview');
  }, [queryId, queryPhone, queryName]);

  const directory = useClinicPatientsQuery(orgId, true, { page, search: debouncedSearch });
  const detail = useClinicPatientsQuery(orgId, Boolean(selectedId), { patientId: selectedId });
  const patients = useMemo(() => directory.data || [], [directory.data]);
  const patient = (detail.data || []).find((item) => item.id === selectedId) || patients.find((item) => item.id === selectedId);
  const draft = selectedId ? drafts[selectedId] || '' : '';

  useEffect(() => {
    if (!Object.values(drafts).some((value) => value.trim())) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [drafts]);

  async function handleSaveNote() {
    if (!selectedId || !draft.trim() || savingNotes[selectedId]) return;
    const patientId = selectedId;
    const submittedDraft = draft;
    setSavingNotes((current) => ({ ...current, [patientId]: true }));
    setNoteErrors((current) => ({ ...current, [patientId]: '' }));
    try {
      await saveNote.mutateAsync({ patientId, note: submittedDraft.trim() });
      setDrafts((current) => current[patientId] === submittedDraft ? { ...current, [patientId]: '' } : current);
      setSavedPatientId(patientId);
    } catch {
      setNoteErrors((current) => ({ ...current, [patientId]: 'Couldn’t save this note. Your draft is kept here; try again.' }));
    } finally { setSavingNotes((current) => ({ ...current, [patientId]: false })); }
  }

  return (
    <div className="flex min-h-full flex-col pb-28 font-sans text-neutral-900">
      <header className="mb-4 flex shrink-0 flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-neutral-950">Patients</h1>
          <p className="mt-0.5 text-xs text-neutral-500">
            Your patient directory. Open a record to view details and notes.
          </p>
        </div>
        <button
          type="button"
          onClick={() => openBooking(true)}
          className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-[#0D2622] px-3.5 py-1.5 text-xs font-medium text-white shadow-2xs hover:bg-[#1E6B56] transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>New patient visit</span>
        </button>
      </header>

      {directory.error && (
        <div role="alert" className="mb-3 flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2 text-xs text-rose-800">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-3.5 w-3.5 text-rose-600" />
            <span>Could not load patients.</span>
          </div>
          <button
            onClick={() => void directory.refetch()}
            className="inline-flex items-center gap-1 font-medium underline hover:text-rose-950"
          >
            <RefreshCw className="h-3 w-3" />
            Retry
          </button>
        </div>
      )}

      {queryPhone && !queryId && !selectedId && (
        <p role="status" className="mb-3 rounded-lg border border-blue-100 bg-blue-50/70 px-3.5 py-2 text-xs text-blue-800">
          Choose the correct patient below. A contact number can be shared by several people.
        </p>
      )}

      <div className="w-full">
        {directory.isLoading && patients.length === 0 ? (
          <PatientsDirectorySkeleton />
        ) : (
          <PatientList
            patients={patients}
            selectedPatientId={selectedId}
            isLoading={directory.isLoading}
            searchQuery={search}
            onSearchChange={setSearch}
            onSelectPatient={(id) => {
              setSelectedId(id);
              setActiveTab('Overview');
            }}
          />
        )}
      </div>

      <footer className="flex items-center justify-between gap-3 pt-5 pb-10 text-xs text-neutral-500">
        <span className="font-mono text-[11px] text-neutral-500">
          Page {page} · {patients.length} patients
        </span>
        <div className="flex items-center gap-2">
          <button
            disabled={page === 1 || directory.isLoading}
            onClick={() => setPage(page - 1)}
            className="inline-flex items-center gap-1 min-h-8 rounded-md border border-neutral-200 bg-white px-2.5 text-xs text-neutral-700 hover:bg-neutral-50 disabled:opacity-40 transition-colors shadow-2xs"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            <span>Previous</span>
          </button>
          <button
            disabled={patients.length < 50 || directory.isLoading}
            onClick={() => setPage(page + 1)}
            className="inline-flex items-center gap-1 min-h-8 rounded-md border border-neutral-200 bg-white px-2.5 text-xs text-neutral-700 hover:bg-neutral-50 disabled:opacity-40 transition-colors shadow-2xs"
          >
            <span>Next</span>
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </footer>

      {selectedId && !patient && detail.isLoading && (
        <p role="status" className="mt-3 text-xs text-neutral-500">Opening patient record…</p>
      )}
      {selectedId && !patient && !detail.isLoading && (
        <p role="alert" className="mt-3 text-xs text-rose-700">
          This patient record could not be opened.{' '}
          <button onClick={() => void detail.refetch()} className="underline">Try again</button>
          <button onClick={() => setSelectedId(null)} className="ml-3 underline">Dismiss</button>
        </p>
      )}
      {patient && selectedId && (
        <PatientDetailPanel
          patient={patient}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onClose={() => setSelectedId(null)}
          doctorNoteInput={draft}
          onDoctorNoteChange={(value) => {
            setDrafts((current) => ({ ...current, [selectedId]: value }));
            setSavedPatientId(null);
            setNoteErrors((current) => ({ ...current, [selectedId]: '' }));
          }}
          onSaveNote={handleSaveNote}
          isSavingNote={Boolean(savingNotes[selectedId])}
          noteSavedSuccess={savedPatientId === selectedId && !draft}
          noteError={noteErrors[selectedId]}
          canEditNotes={activeRole === 'doctor'}
        />
      )}
    </div>
  );
}

export default function ClinicPatientsPage() {
  return (
    <Suspense fallback={<PatientsPageSkeleton />}>
      <PatientsContent />
    </Suspense>
  );
}
