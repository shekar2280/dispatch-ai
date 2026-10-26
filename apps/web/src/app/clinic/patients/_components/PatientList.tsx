'use client';

import React, { useMemo, useState } from 'react';
import {
  ChevronRight,
  Loader2,
  Phone,
  Users,
  Search,
  X,
  Copy,
  Check,
  ArrowUpDown,
} from 'lucide-react';
import { motion } from 'motion/react';
import { PatientRecordItem } from '../../types';

type PatientWithUI = PatientRecordItem;

interface PatientListProps {
  patients: PatientWithUI[];
  selectedPatientId: string | null;
  isLoading: boolean;
  searchQuery: string;
  onSearchChange: (v: string) => void;
  onSelectPatient: (id: string) => void;
}

type FilterTab = 'all' | 'visited' | 'new';
type SortField = 'recent' | 'visits' | 'name';

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'PT';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function PatientList({
  patients,
  selectedPatientId,
  isLoading,
  searchQuery,
  onSearchChange,
  onSelectPatient,
}: PatientListProps) {
  const [filterTab, setFilterTab] = useState<FilterTab>('all');
  const [selectedBloodGroup, setSelectedBloodGroup] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<SortField>('recent');
  const [copiedPhone, setCopiedPhone] = useState<string | null>(null);

  const bloodGroups = useMemo(() => {
    const set = new Set<string>();
    patients.forEach((p) => {
      if (p.blood_group) set.add(p.blood_group.trim());
    });
    return Array.from(set).sort();
  }, [patients]);

  const counts = useMemo(() => {
    const total = patients.length;
    const visited = patients.filter((p) => p.total_visits > 0 && p.last_visit !== 'Never').length;
    const newCount = patients.filter((p) => p.total_visits === 0 || p.last_visit === 'Never').length;
    return { total, visited, newCount };
  }, [patients]);

  const filteredPatients = useMemo(() => {
    let list = [...patients];

    if (filterTab === 'visited') {
      list = list.filter((p) => p.total_visits > 0 && p.last_visit !== 'Never');
    } else if (filterTab === 'new') {
      list = list.filter((p) => p.total_visits === 0 || p.last_visit === 'Never');
    }

    if (selectedBloodGroup !== 'ALL') {
      list = list.filter((p) => (p.blood_group || '').trim() === selectedBloodGroup);
    }

    list.sort((a, b) => {
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'visits') return (b.total_visits || 0) - (a.total_visits || 0);
      return 0;
    });

    return list;
  }, [patients, filterTab, selectedBloodGroup, sortBy]);

  const handleCopy = (e: React.MouseEvent, phone: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(phone);
    setCopiedPhone(phone);
    setTimeout(() => setCopiedPhone(null), 1400);
  };

  return (
    <section className="flex flex-col rounded-xl border border-neutral-200/90 bg-white shadow-2xs">
      <div className="border-b border-neutral-200/80 px-4 py-3 shrink-0 bg-white space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setFilterTab('all')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                filterTab === 'all'
                  ? 'bg-neutral-900 text-white font-semibold'
                  : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
              }`}
            >
              All Records <span className="opacity-70 ml-1 text-[11px]">({counts.total})</span>
            </button>
            <button
              type="button"
              onClick={() => setFilterTab('visited')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                filterTab === 'visited'
                  ? 'bg-neutral-900 text-white font-semibold'
                  : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
              }`}
            >
              Visited <span className="opacity-70 ml-1 text-[11px]">({counts.visited})</span>
            </button>
            <button
              type="button"
              onClick={() => setFilterTab('new')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                filterTab === 'new'
                  ? 'bg-neutral-900 text-white font-semibold'
                  : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
              }`}
            >
              New Patients <span className="opacity-70 ml-1 text-[11px]">({counts.newCount})</span>
            </button>
          </div>

          <div className="flex items-center gap-2 self-end sm:self-auto">
            {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-neutral-400" />}
            <div className="flex items-center gap-1.5 text-xs text-neutral-500">
              <ArrowUpDown className="h-3.5 w-3.5 text-neutral-400" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortField)}
                className="rounded-lg border border-neutral-200 bg-white px-2 py-1 text-xs text-neutral-800 outline-none hover:border-neutral-300 focus:border-neutral-900 transition-colors"
              >
                <option value="recent">Recent Visit</option>
                <option value="visits">Most Visits</option>
                <option value="name">Name (A-Z)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              aria-label="Search patients"
              placeholder="Search by patient name, phone number, or age…"
              className="h-9 w-full rounded-lg border border-neutral-200 bg-neutral-50/50 pl-9 pr-8 text-xs text-neutral-900 outline-none placeholder:text-neutral-400 focus:bg-white focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-700"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {bloodGroups.length > 0 && (
            <div className="flex items-center gap-1 overflow-x-auto py-0.5 shrink-0">
              <span className="text-[11px] font-medium text-neutral-400 mr-1 hidden sm:inline">Blood:</span>
              <button
                type="button"
                onClick={() => setSelectedBloodGroup('ALL')}
                className={`rounded-md px-2 py-1 text-[11px] font-mono font-medium transition-colors ${
                  selectedBloodGroup === 'ALL'
                    ? 'bg-neutral-800 text-white'
                    : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200/80'
                }`}
              >
                All
              </button>
              {bloodGroups.map((group) => (
                <button
                  key={group}
                  type="button"
                  onClick={() => setSelectedBloodGroup(selectedBloodGroup === group ? 'ALL' : group)}
                  className={`rounded-md px-2 py-1 text-[11px] font-mono font-medium transition-colors ${
                    selectedBloodGroup === group
                      ? 'bg-rose-700 text-white'
                      : 'bg-rose-50 text-rose-700 border border-rose-200/70 hover:bg-rose-100/80'
                  }`}
                >
                  {group}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="hidden grid-cols-[1.5fr_0.7fr_1fr_1fr_32px] gap-4 border-b border-neutral-200/80 bg-neutral-50/70 px-4 py-2.5 text-xs font-medium text-neutral-500 md:grid shrink-0">
        <span>Patient</span>
        <span>Blood Group</span>
        <span>Contact</span>
        <span>Visit History</span>
        <span />
      </div>

      <div className="divide-y divide-neutral-100">
        {isLoading && patients.length === 0 ? (
          <div className="flex min-h-[300px] items-center justify-center py-16">
            <div className="flex items-center gap-2 text-xs font-medium text-neutral-400">
              <Loader2 className="h-4 w-4 animate-spin text-neutral-500" />
              Loading directory...
            </div>
          </div>
        ) : filteredPatients.length === 0 ? (
          <div className="flex min-h-[300px] flex-col items-center justify-center px-6 py-16 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-neutral-100">
              <Users className="h-4 w-4 text-neutral-400" />
            </div>
            <p className="text-sm font-semibold text-neutral-800">No patients found</p>
            <p className="mt-1 text-xs text-neutral-400 max-w-xs">
              {searchQuery
                ? `No results matching "${searchQuery}". Try another name or phone number.`
                : 'No patients found in this category.'}
            </p>
            {(searchQuery || selectedBloodGroup !== 'ALL' || filterTab !== 'all') && (
              <button
                type="button"
                onClick={() => {
                  onSearchChange('');
                  setSelectedBloodGroup('ALL');
                  setFilterTab('all');
                }}
                className="mt-3 text-xs font-medium text-neutral-900 underline hover:text-neutral-600"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          filteredPatients.map((patient) => {
            const active = selectedPatientId === patient.id;
            const initials = getInitials(patient.name);
            const isNever = patient.last_visit === 'Never' || patient.total_visits === 0;

            return (
              <motion.div
                layout="position"
                key={patient.id}
                onClick={() => onSelectPatient(patient.id)}
                className={`group relative grid w-full grid-cols-1 gap-2.5 px-4 py-2.5 text-left transition-colors md:grid-cols-[1.5fr_0.7fr_1fr_1fr_32px] md:items-center md:gap-4 cursor-pointer ${
                  active ? 'bg-neutral-100/80' : 'hover:bg-neutral-50/70'
                }`}
              >
                {active && (
                  <span className="absolute bottom-0 left-0 top-0 w-1 rounded-r-md bg-[#0D2622]" />
                )}

                <div className="flex items-center gap-3 min-w-0 pr-2">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#E3EBE0] text-xs font-semibold text-[#1E6B56] border border-emerald-200/50">
                    {initials}
                  </span>
                  <div className="min-w-0">
                    <p
                      className={`truncate text-sm font-medium transition-colors ${
                        active ? 'text-neutral-950 font-semibold' : 'text-neutral-800 group-hover:text-neutral-950'
                      }`}
                    >
                      {patient.name}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-neutral-400">
                      {patient.age_gender}
                      {patient.dob && ` · DOB: ${patient.dob}`}
                    </p>
                  </div>
                </div>

                <div className="hidden md:flex items-center min-w-0">
                  {patient.blood_group ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-rose-50 text-rose-700 border border-rose-200/70">
                      {patient.blood_group}
                    </span>
                  ) : (
                    <span className="text-xs text-neutral-400 italic">Not recorded</span>
                  )}
                </div>

                <div className="hidden md:flex items-center gap-1.5 min-w-0">
                  <Phone className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
                  <span className="truncate text-xs font-mono text-neutral-600">
                    {patient.phone}
                  </span>
                  <button
                    type="button"
                    aria-label={`Copy phone for ${patient.name}`}
                    onClick={(e) => handleCopy(e, patient.phone)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 text-neutral-400 hover:text-neutral-700 rounded"
                  >
                    {copiedPhone === patient.phone ? (
                      <Check className="h-3 w-3 text-emerald-600" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                </div>

                <div className="hidden md:block min-w-0">
                  <p
                    className={`text-xs font-medium truncate ${
                      isNever ? 'text-amber-700' : 'text-neutral-700'
                    }`}
                  >
                    {isNever ? 'Never visited' : patient.last_visit}
                  </p>
                  <p className="mt-0.5 text-[11px] text-neutral-400 truncate">
                    {patient.total_visits} {patient.total_visits === 1 ? 'visit' : 'visits'}
                  </p>
                </div>

                <div className="hidden md:flex items-center justify-end">
                  <ChevronRight
                    className={`h-4 w-4 transition-transform ${
                      active
                        ? 'text-neutral-900 translate-x-0.5'
                        : 'text-neutral-300 group-hover:text-neutral-600 group-hover:translate-x-0.5'
                    }`}
                  />
                </div>

                <div className="flex items-center justify-between pt-1 border-t border-neutral-100 md:hidden">
                  <div className="flex items-center gap-2">
                    {patient.blood_group && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-rose-50 text-rose-700 border border-rose-200">
                        {patient.blood_group}
                      </span>
                    )}
                    <span className="text-xs text-neutral-500 font-mono">
                      {patient.phone}
                    </span>
                  </div>
                  <span className="text-xs text-neutral-500">
                    {isNever ? 'Never visited' : patient.last_visit}
                  </span>
                </div>
              </motion.div>
            );
          })
        )}
      </div>
    </section>
  );
}
