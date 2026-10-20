import React from 'react';
import { useRouter } from 'next/navigation';
import { Plus, History } from 'lucide-react';
import {
  SLOT_DURATIONS, BUFFER_OPTIONS, MAX_PATIENT_OPTIONS, DEFAULT_WEEKLY_HOURS,
} from '../../constants';
import { TimePicker } from './TimePicker';
import { useClinicSettings } from '../../_context/ClinicSettingsContext';
import { ALL_CURRENCIES } from '@/lib/country-metadata';
import { WEEKDAYS } from '@/lib/weekly-schedule';

const ORDERED_DAYS = WEEKDAYS;

export function OpdScheduleSection() {
  const {
    slotDuration, setSlotDuration,
    slotBuffer, setSlotBuffer,
    maxDailyPatients, setMaxDailyPatients,
    consultationFee, setConsultationFee,
    currencyCode, currencySymbol, handleCurrencyChange,
    weeklyHours,
    handleDayToggle,
    handleTimeChange,
  } = useClinicSettings();

  const router = useRouter();

  const slotMin = Number(slotDuration);
  const gapMin = Number(slotBuffer);
  const openDayCount = ORDERED_DAYS.filter(day => weeklyHours[day]?.isOpen).length;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-1">
        <div>
          <h2 className="text-base font-bold text-neutral-950">Appointments & consultation hours</h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Set appointment lengths, daily patient capacity, and your weekly hours.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          <button
            type="button"
            onClick={() => {
              router.push('/clinic/schedule/history?action=leave');
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold cursor-pointer transition-all shadow-2xs active:scale-95"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Schedule Leave</span>
          </button>

          <button
            type="button"
            onClick={() => {
              router.push('/clinic/schedule/history?action=special_hours');
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-neutral-50 border border-neutral-200/90 text-neutral-800 text-xs font-semibold cursor-pointer transition-all shadow-2xs active:scale-95"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Extended Hours</span>
          </button>

          <button
            type="button"
            onClick={() => {
              router.push('/clinic/schedule/history?type=all');
            }}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-neutral-100 hover:bg-neutral-200/80 border border-neutral-200 text-neutral-700 text-xs font-semibold cursor-pointer transition-all shadow-2xs active:scale-95"
          >
            <History className="w-3.5 h-3.5 text-neutral-500" />
            <span>History</span>
          </button>
        </div>
      </div>

      <div className="bg-white border border-neutral-200/90 rounded-2xl shadow-xs overflow-hidden">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-neutral-100">
          <div className="p-4 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-neutral-900">Consultation Fee</span>
                <span className="text-[11px] font-extrabold text-neutral-950 bg-neutral-100 px-2 py-0.5 rounded-md border border-neutral-200/70">
                  {currencySymbol}{consultationFee || '500'}
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-0.5">Standard per-visit charge</p>
            </div>

            <div className="flex items-center rounded-lg border border-neutral-200 bg-neutral-50/50 hover:bg-white focus-within:bg-white focus-within:border-neutral-950 focus-within:ring-1 focus-within:ring-neutral-950/10 transition-all h-8 overflow-hidden">
              <div className="relative shrink-0 border-r border-neutral-200 bg-neutral-100/70 hover:bg-neutral-200/60 transition-colors flex items-center h-full">
                <select
                  value={currencyCode}
                  onChange={(e) => handleCurrencyChange(e.target.value)}
                  className="h-full pl-2 pr-4 text-xs font-bold text-neutral-800 bg-transparent outline-none cursor-pointer appearance-none"
                  title={`Currency: ${currencyCode}`}
                >
                  {ALL_CURRENCIES.map((cur) => (
                    <option key={cur.code} value={cur.code}>
                      {cur.symbol} {cur.code}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-1 flex items-center text-neutral-400 text-[10px]">
                  ▾
                </div>
              </div>
              <input
                type="number"
                value={consultationFee}
                onChange={(e) => setConsultationFee(e.target.value)}
                placeholder="500"
                className="w-full px-2.5 text-xs font-bold text-neutral-900 bg-transparent outline-none"
              />
            </div>
          </div>

          <div className="p-4 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-neutral-900">Duration</span>
                <span className="text-[11px] font-extrabold text-neutral-950 bg-neutral-100 px-2 py-0.5 rounded-md border border-neutral-200/70">
                  {slotMin} min
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-0.5">Time per patient slot</p>
            </div>

            <div className="grid grid-cols-5 gap-1 p-0.5 bg-neutral-100 rounded-lg border border-neutral-200/60 h-8 items-center">
              {SLOT_DURATIONS.map((o) => {
                const isSelected = slotDuration === o.value;
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setSlotDuration(o.value)}
                    className={`h-7 rounded-md text-[11px] font-semibold transition-all cursor-pointer flex items-center justify-center ${
                      isSelected
                        ? 'bg-neutral-950 text-white shadow-2xs'
                        : 'text-neutral-600 hover:text-neutral-950 hover:bg-white/60'
                    }`}
                  >
                    {o.value}m
                  </button>
                );
              })}
            </div>
          </div>

          <div className="p-4 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-neutral-900">Turnaround Buffer</span>
                <span className="text-[11px] font-extrabold text-neutral-950 bg-neutral-100 px-2 py-0.5 rounded-md border border-neutral-200/70">
                  {gapMin} min
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-0.5">Gap between appointments</p>
            </div>

            <div className="grid grid-cols-3 gap-1 p-0.5 bg-neutral-100 rounded-lg border border-neutral-200/60 h-8 items-center">
              {BUFFER_OPTIONS.map((option) => {
                const isSelected = slotBuffer === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setSlotBuffer(option.value)}
                    className={`h-7 rounded-md text-[11px] font-semibold transition-all cursor-pointer flex items-center justify-center ${
                      isSelected
                        ? 'bg-neutral-950 text-white shadow-2xs'
                        : 'text-neutral-600 hover:text-neutral-950 hover:bg-white/60'
                    }`}
                  >
                    {option.value}m
                  </button>
                );
              })}
            </div>
          </div>

          <div className="p-4 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-neutral-900">Daily Patient Cap</span>
                <span className="text-[11px] font-extrabold text-neutral-950 bg-neutral-100 px-2 py-0.5 rounded-md border border-neutral-200/70">
                  {maxDailyPatients === '999' ? 'Unlimited' : `${maxDailyPatients} / day`}
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-0.5">Maximum patients per day</p>
            </div>

            <div className="grid grid-cols-5 gap-1 p-0.5 bg-neutral-100 rounded-lg border border-neutral-200/60 h-8 items-center">
              {MAX_PATIENT_OPTIONS.map((o) => {
                const isSelected = maxDailyPatients === o.value;
                const displayVal = o.value === '999' ? '∞' : o.value;
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setMaxDailyPatients(o.value)}
                    className={`h-7 rounded-md text-[11px] font-semibold transition-all cursor-pointer flex items-center justify-center ${
                      isSelected
                        ? 'bg-neutral-950 text-white shadow-2xs'
                        : 'text-neutral-600 hover:text-neutral-950 hover:bg-white/60'
                    }`}
                  >
                    {displayVal}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-bold text-neutral-950">Recurring weekly hours</h3>
            <span className="text-xs text-neutral-500">{openDayCount} of 7 days enabled</span>
          </div>
          <p className="text-xs text-neutral-500 mt-0.5">
            These hours repeat every week. Set each day independently; use Schedule Leave or Extended Hours for a specific date.
          </p>
        </div>

        {openDayCount === 0 && (
          <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
            No recurring appointment hours are enabled. Turn on a day and set its consultation times to accept bookings.
          </div>
        )}

        <div className="bg-white border border-neutral-200/90 rounded-2xl shadow-xs divide-y divide-neutral-100">
          {ORDERED_DAYS.map((day) => {
            const sched = weeklyHours[day] || DEFAULT_WEEKLY_HOURS[day];
            return (
              <div
                key={day}
                className="px-5 py-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-neutral-50/70 transition-colors"
              >
                <div className="flex items-center gap-3.5 min-w-[170px] shrink-0">
                  <button
                    type="button"
                    role="switch"
                    aria-label={`${day} appointments`}
                    aria-checked={sched.isOpen}
                    onClick={() => handleDayToggle(day)}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                      sched.isOpen ? 'bg-neutral-950' : 'bg-neutral-200'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-2xs transition duration-200 ${
                        sched.isOpen ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>

                  <span className="text-xs font-bold text-neutral-900 w-20">{day}</span>

                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10.5px] font-bold border ${
                      sched.isOpen
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200/80'
                        : 'bg-neutral-100 text-neutral-500 border-neutral-200/60'
                    }`}
                  >
                    {sched.isOpen ? (
                      <>
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        <span>Open weekly</span>
                      </>
                    ) : (
                      <span>Weekly day off</span>
                    )}
                  </span>
                </div>

                {sched.isOpen ? (
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <div className="flex items-center gap-2 bg-neutral-50/90 border border-neutral-200/70 rounded-xl px-3 py-1.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">Morning</span>
                      <TimePicker value={sched.morningStart} onChange={(val) => handleTimeChange(day, 'morningStart', val)} />
                      <span className="text-neutral-400 text-xs font-medium">→</span>
                      <TimePicker value={sched.morningEnd} onChange={(val) => handleTimeChange(day, 'morningEnd', val)} />
                    </div>

                    <div className="flex items-center gap-2 bg-neutral-50/90 border border-neutral-200/70 rounded-xl px-3 py-1.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">Evening</span>
                      <TimePicker value={sched.eveningStart} onChange={(val) => handleTimeChange(day, 'eveningStart', val)} align="right" />
                      <span className="text-neutral-400 text-xs font-medium">→</span>
                      <TimePicker value={sched.eveningEnd} onChange={(val) => handleTimeChange(day, 'eveningEnd', val)} align="right" />
                    </div>
                  </div>
                ) : (
                  <div className="text-left md:text-right py-1">
                    <span className="text-xs text-neutral-400 italic">
                      No recurring appointments on {day}s
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
}
