'use client';

import React from 'react';

export function DashboardSkeleton() {
  return (
    <div className="min-h-full flex flex-col gap-5 font-sans text-[#0D2622] pb-16 animate-pulse select-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-[#0D2622]">
            Consultation Desk
          </h1>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5 font-normal">
            Active patient chamber, quick clinical notes, and live queue management
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-5 flex-1">
        <div className="rounded-2xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] p-6 shadow-xs flex flex-col gap-5">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-[rgba(13,38,34,0.08)] pb-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-6 w-48 bg-[rgba(13,38,34,0.12)] rounded-lg" />
                <div className="h-5 w-16 bg-[rgba(13,38,34,0.06)] rounded" />
              </div>
              <div className="h-3.5 w-72 bg-[rgba(13,38,34,0.06)] rounded" />
            </div>
            <div className="flex items-center gap-2">
              <div className="h-8 w-32 rounded-lg bg-[#0D2622]" />
              <div className="h-8 w-28 rounded-lg bg-[rgba(13,38,34,0.06)]" />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className="lg:col-span-8 flex flex-col gap-4">
              <div className="rounded-xl border border-[rgba(13,38,34,0.12)] bg-[#E3EBE0]/40 p-4 space-y-2">
                <div className="h-3.5 w-32 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-10 w-full bg-[#FFFFFF] rounded-lg border border-[rgba(13,38,34,0.12)]" />
              </div>
              <div className="rounded-xl border border-[rgba(13,38,34,0.12)] bg-[#E3EBE0]/40 p-4 space-y-2">
                <div className="h-3.5 w-28 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-44 w-full bg-[#FFFFFF] rounded-lg border border-[rgba(13,38,34,0.12)]" />
              </div>
              <div className="flex justify-end">
                <div className="h-8 w-28 rounded-lg bg-[rgba(13,38,34,0.12)]" />
              </div>
            </div>

            <div className="lg:col-span-4 rounded-xl border border-[rgba(13,38,34,0.12)] bg-[#E3EBE0]/30 p-4 space-y-3 h-[380px]">
              <div className="flex items-center justify-between border-b border-[rgba(13,38,34,0.08)] pb-2.5">
                <div className="h-4 w-36 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-4 w-16 bg-[rgba(13,38,34,0.12)] rounded-full" />
              </div>
              <div className="space-y-2.5">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="p-3 rounded-lg bg-[#FFFFFF] border border-[rgba(13,38,34,0.12)] space-y-1.5">
                    <div className="h-3.5 w-24 bg-[rgba(13,38,34,0.12)] rounded" />
                    <div className="h-3 w-40 bg-[rgba(13,38,34,0.06)] rounded" />
                    <div className="h-6 w-full bg-[#E3EBE0]/40 rounded" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ScheduleTableRowsSkeleton() {
  return (
    <div className="divide-y divide-[rgba(13,38,34,0.08)] animate-pulse select-none">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="px-4 py-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-14 h-7 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-lg shrink-0" />
            <div className="space-y-1.5 flex-1 min-w-0">
              <div className="h-3.5 bg-[rgba(13,38,34,0.12)] rounded w-36" />
              <div className="h-2.5 bg-[rgba(13,38,34,0.06)] rounded w-48" />
            </div>
          </div>
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="w-20 h-6 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-full" />
            <div className="w-20 h-6 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-xl" />
            <div className="w-24 h-8 bg-[#0D2622] rounded-xl" />
            <div className="w-8 h-8 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ScheduleTableSkeleton() {
  return (
    <div className="bg-[#FFFFFF] rounded-2xl border border-[rgba(13,38,34,0.12)] shadow-xs w-full relative overflow-hidden select-none">
      <div className="p-3 sm:px-4 sm:py-3 border-b border-[rgba(13,38,34,0.1)] flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#E3EBE0]/50 rounded-t-2xl">
        <div className="flex items-center p-0.5 rounded-xl bg-[rgba(13,38,34,0.08)]">
          <span className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-[#FFFFFF] text-[#0D2622] shadow-xs">
            Waiting Room
          </span>
          <span className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-[rgba(13,38,34,0.65)]">
            Upcoming
          </span>
          <span className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-[rgba(13,38,34,0.65)]">
            Completed
          </span>
          <span className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-[rgba(13,38,34,0.65)]">
            All Patients
          </span>
        </div>
        <div className="relative w-full sm:w-64">
          <div className="h-9 pl-9 pr-4 text-xs bg-[#FFFFFF] border border-[rgba(13,38,34,0.12)] rounded-xl flex items-center text-[rgba(13,38,34,0.4)]">
            Search patient, phone, token...
          </div>
        </div>
      </div>

      <div className="px-4 py-2.5 bg-[#E3EBE0]/30 border-b border-[rgba(13,38,34,0.08)] flex items-center justify-between">
        <span className="text-xs font-bold text-[#0D2622] tracking-tight">Checked-in Patients</span>
        <span className="text-[11px] font-medium text-[rgba(13,38,34,0.65)]">Ready for consultation</span>
      </div>

      <ScheduleTableRowsSkeleton />
    </div>
  );
}

export function SchedulePageSkeleton() {
  return (
    <div className="w-full space-y-4 pb-12 font-sans text-[#0D2622] select-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#0D2622]">Clinic Schedule</h1>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5">Appointments, check-ins, and consultation queue</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <div className="lg:col-span-8 space-y-4 w-full min-w-0">
          <ScheduleTableSkeleton />
        </div>

        <div className="lg:col-span-4 space-y-3 w-full min-w-0">
          <div className="rounded-2xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] p-4 shadow-xs space-y-3 animate-pulse">
            <div className="flex items-center justify-between border-b border-[rgba(13,38,34,0.08)] pb-3">
              <span className="text-xs font-bold text-[#0D2622]">OPD Slot Matrix</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="h-14 rounded-xl bg-[#E3EBE0]/30 border border-[rgba(13,38,34,0.08)] p-2.5 space-y-1.5">
                  <div className="h-3 w-16 bg-[rgba(13,38,34,0.12)] rounded" />
                  <div className="h-2.5 w-12 bg-[rgba(13,38,34,0.06)] rounded" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function CallsPageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse select-none">
      <div className="space-y-2.5">
        <div className="flex items-center gap-2.5 px-1 pt-1">
          <div className="h-3.5 w-20 bg-[rgba(13,38,34,0.12)] rounded" />
          <div className="h-3.5 w-14 bg-[rgba(13,38,34,0.06)] rounded-full" />
          <div className="h-px bg-[rgba(13,38,34,0.1)] flex-1" />
        </div>

        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="rounded-2xl border border-[rgba(13,38,34,0.12)] p-3.5 sm:p-4 bg-[#FFFFFF] shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-xl bg-[#E3EBE0]/50 border border-[rgba(13,38,34,0.12)] shrink-0" />
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="h-4 w-32 bg-[rgba(13,38,34,0.12)] rounded font-mono" />
                    <div className="h-3.5 w-28 bg-[rgba(13,38,34,0.06)] rounded" />
                  </div>
                  <div className="h-3 w-48 bg-[rgba(13,38,34,0.06)] rounded" />
                </div>
              </div>
              <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
                <div className="w-20 h-6 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.1)] rounded-full" />
                <div className="w-20 h-6 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.1)] rounded-full" />
                <div className="w-20 h-8 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-xl" />
                <div className="w-24 h-8 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-xl" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function PatientsDirectorySkeleton() {
  return (
    <div className="flex-1 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(420px,1.1fr)] min-h-0 animate-pulse select-none">
      <section className="flex flex-col overflow-hidden rounded-xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] shadow-xs h-full">
        <div className="border-b border-[rgba(13,38,34,0.1)] p-4 shrink-0 bg-[#FFFFFF] space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#0D2622]">Directory</h2>
            <div className="h-4 w-16 bg-[rgba(13,38,34,0.06)] rounded-lg" />
          </div>
          <div className="h-9 w-full bg-[#E3EBE0]/40 border border-[rgba(13,38,34,0.12)] rounded-lg" />
        </div>
        <div className="divide-y divide-[rgba(13,38,34,0.08)] flex-1 overflow-hidden">
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="p-3.5 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-[#E3EBE0]/50 border border-[rgba(13,38,34,0.12)]" />
                <div className="space-y-1.5">
                  <div className="h-3.5 w-32 bg-[rgba(13,38,34,0.12)] rounded" />
                  <div className="h-2.5 w-24 bg-[rgba(13,38,34,0.06)] rounded" />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-5 w-12 bg-[rgba(13,38,34,0.06)] rounded-md" />
                <div className="w-4 h-4 bg-[rgba(13,38,34,0.12)] rounded" />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="hidden xl:flex flex-col rounded-xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] shadow-xs p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-[rgba(13,38,34,0.08)] pb-4">
          <div className="space-y-2">
            <div className="h-6 w-44 bg-[rgba(13,38,34,0.12)] rounded-lg" />
            <div className="h-3 w-56 bg-[rgba(13,38,34,0.06)] rounded" />
          </div>
          <div className="h-6 w-20 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-full" />
        </div>
        <div className="grid grid-cols-4 gap-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-16 bg-[#E3EBE0]/30 rounded-xl border border-[rgba(13,38,34,0.08)] p-2.5 space-y-1">
              <div className="h-2.5 w-12 bg-[rgba(13,38,34,0.12)] rounded" />
              <div className="h-4 w-14 bg-[rgba(13,38,34,0.16)] rounded" />
            </div>
          ))}
        </div>
        <div className="h-28 bg-[#E3EBE0]/30 rounded-xl border border-[rgba(13,38,34,0.08)] p-3 space-y-2">
          <div className="h-3 w-28 bg-[rgba(13,38,34,0.12)] rounded" />
          <div className="h-14 w-full bg-[#FFFFFF] rounded border border-[rgba(13,38,34,0.12)]" />
        </div>
        <div className="h-36 bg-[#E3EBE0]/30 rounded-xl border border-[rgba(13,38,34,0.08)]" />
      </section>
    </div>
  );
}

export function PatientsPageSkeleton() {
  return (
    <div className="min-h-full lg:h-[calc(100vh-80px)] flex flex-col font-sans text-[#0D2622] pb-24 lg:pb-4 select-none">
      <div className="mb-4 flex flex-col justify-between gap-4 sm:flex-row sm:items-end shrink-0">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-[#0D2622]">Patients</h1>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5 font-normal">
            Manage clinical records, consultation history, and patient notes.
          </p>
        </div>
      </div>
      <PatientsDirectorySkeleton />
    </div>
  );
}

export function ActionCenterSkeleton() {
  return (
    <div className="min-h-full flex flex-col gap-4 font-sans text-[#0D2622] pb-24 lg:pb-12 select-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold tracking-tight text-[#0D2622]">
              Action Center
            </h1>
          </div>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5 font-normal">
            Patient requests, prescription renewals, and urgent alerts flagged by Tulsi.
          </p>
        </div>
        <div className="flex items-center p-0.5 rounded-lg bg-[rgba(13,38,34,0.08)]">
          <span className="px-3 py-1 rounded-md text-xs font-semibold bg-[#FFFFFF] text-[#0D2622] shadow-xs">
            Pending
          </span>
          <span className="px-3 py-1 rounded-md text-xs font-semibold text-[rgba(13,38,34,0.65)]">
            All
          </span>
          <span className="px-3 py-1 rounded-md text-xs font-semibold text-[rgba(13,38,34,0.65)]">
            Resolved
          </span>
        </div>
      </div>

      <div className="space-y-3 animate-pulse">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="p-4 rounded-xl bg-[#FFFFFF] border border-[rgba(13,38,34,0.12)] shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="h-4 w-32 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-3.5 w-24 bg-[rgba(13,38,34,0.06)] rounded" />
              </div>
              <div className="h-5 w-28 rounded-md bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)]" />
            </div>
            <div className="h-4 w-3/4 bg-[rgba(13,38,34,0.06)] rounded" />
            <div className="flex items-center justify-between pt-2 border-t border-[rgba(13,38,34,0.08)]">
              <div className="h-3 w-28 bg-[rgba(13,38,34,0.06)] rounded" />
              <div className="flex items-center gap-2">
                <div className="h-8 w-24 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-lg" />
                <div className="h-8 w-24 bg-[#0D2622] rounded-lg" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RevenuePageSkeleton() {
  return (
    <div className="w-full space-y-4 pb-24 lg:pb-12 text-[#0D2622] select-none">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 animate-pulse">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="p-3.5 rounded-xl bg-[#FFFFFF] border border-[rgba(13,38,34,0.12)] shadow-xs space-y-2">
            <div className="flex items-center justify-between">
              <div className="h-3 bg-[rgba(13,38,34,0.12)] rounded w-20" />
              <div className="w-3.5 h-3.5 bg-[rgba(13,38,34,0.12)] rounded" />
            </div>
            <div className="h-7 bg-[rgba(13,38,34,0.12)] rounded w-24" />
            <div className="mt-2 pt-2 border-t border-[rgba(13,38,34,0.08)]">
              <div className="h-2.5 bg-[rgba(13,38,34,0.06)] rounded w-28" />
            </div>
          </div>
        ))}
      </div>

      <div className="bg-[#FFFFFF] rounded-xl border border-[rgba(13,38,34,0.12)] shadow-xs overflow-hidden w-full">
        <div className="hidden md:grid md:grid-cols-12 px-4 py-2 bg-[#E3EBE0]/40 border-b border-[rgba(13,38,34,0.08)] text-[11px] font-semibold text-[rgba(13,38,34,0.65)] uppercase tracking-wider">
          <div className="col-span-2">Time &amp; Date</div>
          <div className="col-span-3">Patient</div>
          <div className="col-span-2">Booking Type</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-1">Amount</div>
          <div className="col-span-2 text-right">Settlement Action</div>
        </div>

        <div className="divide-y divide-[rgba(13,38,34,0.08)] animate-pulse">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="px-4 py-2.5 flex flex-col md:grid md:grid-cols-12 md:items-center gap-2 md:gap-0">
              <div className="col-span-2 flex items-center gap-2">
                <div className="h-5 w-14 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-md" />
                <div className="h-3 w-16 bg-[rgba(13,38,34,0.06)] rounded" />
              </div>
              <div className="col-span-3 space-y-1">
                <div className="h-3.5 w-32 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-2.5 w-24 bg-[rgba(13,38,34,0.06)] rounded" />
              </div>
              <div className="col-span-2">
                <div className="h-5 w-24 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded" />
              </div>
              <div className="col-span-2">
                <div className="h-5 w-24 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-full" />
              </div>
              <div className="col-span-1">
                <div className="h-4 w-12 bg-[rgba(13,38,34,0.12)] rounded" />
              </div>
              <div className="col-span-2 flex justify-end gap-1.5">
                <div className="h-7 w-14 bg-[rgba(13,38,34,0.06)] border border-[rgba(13,38,34,0.12)] rounded-lg" />
                <div className="h-7 w-16 bg-[#0D2622] rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AnalyticsPageSkeleton() {
  return (
    <div className="min-h-full flex flex-col gap-5 font-sans text-[#0D2622] pb-24 lg:pb-16 select-none">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 animate-pulse">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="p-4 rounded-xl bg-[#FFFFFF] border border-[rgba(13,38,34,0.12)] shadow-xs flex flex-col justify-between space-y-3">
            <div className="flex items-center justify-between">
              <div className="h-3 bg-[rgba(13,38,34,0.12)] rounded w-24" />
              <div className="w-4 h-4 bg-[rgba(13,38,34,0.12)] rounded" />
            </div>
            <div className="h-8 bg-[rgba(13,38,34,0.12)] rounded w-20" />
            <div className="h-3 bg-[rgba(13,38,34,0.06)] rounded w-32" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0 animate-pulse">
        <div className="lg:col-span-8 rounded-2xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] p-5 shadow-xs flex flex-col justify-between space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[rgba(13,38,34,0.08)]">
            <div className="space-y-1">
              <div className="h-4 bg-[rgba(13,38,34,0.12)] rounded w-56" />
              <div className="h-3 bg-[rgba(13,38,34,0.06)] rounded w-44" />
            </div>
            <div className="w-4 h-4 bg-[rgba(13,38,34,0.12)] rounded" />
          </div>

          <div className="relative flex-1 min-h-[220px] flex flex-col justify-end pt-6 select-none">
            <div className="absolute inset-0 flex flex-col justify-between pointer-events-none pb-7">
              <div className="border-b border-dashed border-[rgba(13,38,34,0.08)] w-full h-1" />
              <div className="border-b border-dashed border-[rgba(13,38,34,0.08)] w-full h-1" />
              <div className="border-b border-[rgba(13,38,34,0.12)] w-full" />
            </div>

            <div className="relative z-10 flex items-end justify-between gap-1.5 h-44 pb-1">
              {[35, 60, 20, 85, 50, 100, 40, 75, 30, 90, 65, 45, 80, 55].map((h, i) => (
                <div key={i} className="flex-1 flex flex-col items-center h-full justify-end">
                  <div style={{ height: `${h}%` }} className="w-full max-w-[12px] bg-[rgba(13,38,34,0.12)] rounded-t-[2px]" />
                </div>
              ))}
            </div>

            <div className="h-5 flex items-center justify-between mt-1 px-1">
              <div className="h-2.5 w-8 bg-[rgba(13,38,34,0.12)] rounded" />
              <div className="h-2.5 w-8 bg-[rgba(13,38,34,0.12)] rounded" />
              <div className="h-2.5 w-8 bg-[rgba(13,38,34,0.12)] rounded" />
              <div className="h-2.5 w-8 bg-[rgba(13,38,34,0.12)] rounded" />
            </div>
          </div>
        </div>

        <div className="lg:col-span-4 rounded-2xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] p-5 shadow-xs flex flex-col justify-between space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[rgba(13,38,34,0.08)]">
            <div className="h-4 bg-[rgba(13,38,34,0.12)] rounded w-32" />
            <div className="w-4 h-4 bg-[rgba(13,38,34,0.12)] rounded" />
          </div>

          <div className="flex flex-col gap-5 py-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="h-3.5 bg-[rgba(13,38,34,0.12)] rounded w-32" />
                  <div className="h-3.5 bg-[rgba(13,38,34,0.12)] rounded w-16" />
                </div>
                <div className="w-full h-2 rounded-full bg-[rgba(13,38,34,0.06)] overflow-hidden">
                  <div className="h-full bg-[rgba(13,38,34,0.18)] rounded-full w-2/3" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SettingsPageSkeleton() {
  return (
    <div className="h-full flex flex-col md:flex-row font-sans text-[#0D2622] min-h-0 bg-[#F1F4EE] select-none">
      <aside className="w-full md:w-[220px] md:shrink-0 border-b md:border-b-0 md:border-r border-[rgba(13,38,34,0.12)] bg-[#FFFFFF]/70 p-2.5 md:p-3.5 space-y-4">
        <div>
          <h2 className="hidden md:block text-[11px] font-bold uppercase tracking-wider text-[rgba(13,38,34,0.45)] px-2.5 pt-1">
            Clinic settings
          </h2>
        </div>
        <div className="space-y-1">
          <div className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-[#0D2622] text-[#F1F4EE]">
            Profile
          </div>
          <div className="px-2.5 py-1.5 rounded-lg text-xs font-medium text-[rgba(13,38,34,0.65)]">
            Appointments &amp; hours
          </div>
          <div className="px-2.5 py-1.5 rounded-lg text-xs font-medium text-[rgba(13,38,34,0.65)]">
            Staff access
          </div>
          <div className="px-2.5 py-1.5 rounded-lg text-xs font-medium text-[rgba(13,38,34,0.65)]">
            Voice &amp; greeting
          </div>
          <div className="px-2.5 py-1.5 rounded-lg text-xs font-medium text-[rgba(13,38,34,0.65)]">
            Plan &amp; usage
          </div>
        </div>
      </aside>

      <main className="flex-1 p-4 md:p-6 space-y-5 animate-pulse">
        <div className="rounded-2xl border border-[rgba(13,38,34,0.12)] bg-[#FFFFFF] p-6 shadow-xs space-y-4">
          <div className="border-b border-[rgba(13,38,34,0.08)] pb-4 space-y-2">
            <div className="h-5 w-44 bg-[rgba(13,38,34,0.12)] rounded-lg" />
            <div className="h-3.5 w-72 bg-[rgba(13,38,34,0.06)] rounded" />
          </div>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-3 w-28 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-10 w-full bg-[#E3EBE0]/30 border border-[rgba(13,38,34,0.1)] rounded-xl" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

export function ArrivalWindowsSkeleton() {
  return (
    <div className="bg-[#FFFFFF] rounded-2xl border border-[rgba(13,38,34,0.12)] shadow-xs p-4 space-y-3.5 animate-pulse select-none">
      <div className="flex items-center justify-between gap-2 border-b border-[rgba(13,38,34,0.08)] pb-3">
        <div className="space-y-1.5">
          <div className="h-3.5 w-32 bg-[rgba(13,38,34,0.12)] rounded" />
          <div className="h-2.5 w-24 bg-[rgba(13,38,34,0.06)] rounded" />
        </div>
        <div className="h-5 w-20 bg-[rgba(13,38,34,0.06)] rounded-full border border-[rgba(13,38,34,0.12)]" />
      </div>

      <div className="p-1 bg-[rgba(13,38,34,0.06)] rounded-xl flex items-center gap-1 border border-[rgba(13,38,34,0.12)]">
        <div className="flex-1 h-7 bg-[#FFFFFF] rounded-lg shadow-xs" />
        <div className="flex-1 h-7 bg-transparent rounded-lg" />
      </div>

      <div className="space-y-2.5 pt-0.5">
        <div className="flex items-center justify-between px-0.5">
          <div className="h-3 w-36 bg-[rgba(13,38,34,0.12)] rounded" />
          <div className="h-4 w-14 bg-[rgba(13,38,34,0.06)] rounded" />
        </div>

        <div className="grid grid-cols-2 gap-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="p-2.5 rounded-xl border border-[rgba(13,38,34,0.12)] bg-[#E3EBE0]/30 flex flex-col justify-between gap-3 h-[76px]"
            >
              <div className="flex items-center justify-between gap-1">
                <div className="h-3.5 w-14 bg-[rgba(13,38,34,0.12)] rounded" />
                <div className="h-3.5 w-12 bg-[rgba(13,38,34,0.06)] rounded" />
              </div>
              <div className="flex items-center justify-between gap-1 pt-1 border-t border-[rgba(13,38,34,0.08)]">
                <div className="flex items-center gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-[rgba(13,38,34,0.12)]" />
                  <div className="w-1.5 h-1.5 rounded-full bg-[rgba(13,38,34,0.12)]" />
                  <div className="h-2.5 w-4 bg-[rgba(13,38,34,0.06)] rounded ml-1" />
                </div>
                <div className="h-3 w-10 bg-[rgba(13,38,34,0.12)] rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
