'use client';

import React from 'react';
import {
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Calendar,
  CalendarClock,
  AlertTriangle,
} from 'lucide-react';
import { ClinicCalendarPopover } from '../../_components/ClinicCalendarPopover';

interface ScheduleHeaderProps {
  isToday: boolean;
  waitingOnlyCount: number;
  inChamberCount: number;
  expectedCount: number;
  dateAppointmentsCount: number;
  selectedDate: string;
  dateLabel: string;
  isCalendarOpen: boolean;
  setIsCalendarOpen: (open: boolean) => void;
  onPrevDay: () => void;
  onNextDay: () => void;
  onSelectDate: (date: string) => void;
  onSelectToday: () => void;
  onOpenEndOfDay: () => void;
  rolloverCount: number;
  onManageOverrides?: () => void;
  onOpenUrgency?: () => void;
}

export function ScheduleHeader({
  isToday,
  waitingOnlyCount,
  inChamberCount,
  expectedCount,
  dateAppointmentsCount,
  selectedDate,
  dateLabel,
  isCalendarOpen,
  setIsCalendarOpen,
  onPrevDay,
  onNextDay,
  onSelectDate,
  onSelectToday,
  onOpenEndOfDay,
  rolloverCount,
  onManageOverrides,
  onOpenUrgency,
}: ScheduleHeaderProps) {
  return (
    <div className="space-y-3 pt-1">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-4 flex-wrap">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-neutral-950">
              Clinic Schedule
            </h1>
            <p className="text-xs text-neutral-500 mt-0.5">
              Appointments, check-ins, and consultation queue
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap self-start md:self-center">
          <div className="flex items-center bg-white border border-neutral-200 rounded-xl p-0.5 shadow-2xs">
            <button
              type="button"
              onClick={onPrevDay}
              className="p-1.5 text-neutral-500 hover:text-black hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
              title="Previous Day"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <div className="relative">
              <button
                type="button"
                onClick={() => setIsCalendarOpen(!isCalendarOpen)}
                className="px-2.5 py-1 text-xs font-medium text-neutral-800 hover:text-black hover:bg-neutral-50 rounded-lg transition-colors flex items-center gap-2 cursor-pointer"
              >
                <Calendar className="w-3.5 h-3.5 text-neutral-500" />
                <span>{dateLabel}</span>
              </button>
              {isCalendarOpen && (
                <ClinicCalendarPopover
                  selectedDate={selectedDate}
                  onSelectDate={(d) => {
                    onSelectDate(d);
                    setIsCalendarOpen(false);
                  }}
                  onClose={() => setIsCalendarOpen(false)}
                />
              )}
            </div>

            <button
              type="button"
              onClick={onNextDay}
              className="p-1.5 text-neutral-500 hover:text-black hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
              title="Next Day"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {!isToday && (
            <button
              type="button"
              onClick={onSelectToday}
              className="px-2.5 py-1 text-xs font-medium text-neutral-800 bg-white border border-neutral-200 rounded-xl hover:bg-neutral-50 transition-colors shadow-2xs cursor-pointer"
            >
              Today
            </button>
          )}

          {onManageOverrides && (
            <button
              type="button"
              onClick={onManageOverrides}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl border border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50 text-xs font-medium transition-colors shadow-2xs cursor-pointer"
            >
              <CalendarClock className="w-3.5 h-3.5 text-neutral-500" />
              <span>Schedule changes</span>
            </button>
          )}

          {isToday && onOpenUrgency && (
            <button
              type="button"
              onClick={onOpenUrgency}
              className="flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900 shadow-2xs transition-colors hover:bg-amber-100"
            >
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>Urgent case</span>
            </button>
          )}

          {isToday && (
            <button
              type="button"
              onClick={onOpenEndOfDay}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl border border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50 text-xs font-medium transition-colors shadow-2xs cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5 text-neutral-500" />
              <span>Day Wrap-up</span>
            </button>
          )}
        </div>
      </div>

      {!isToday && rolloverCount > 0 && (
        <div className="p-3.5 rounded-2xl bg-gradient-to-r from-purple-50/90 via-white to-purple-50/40 border border-purple-200/90 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs animate-in fade-in duration-150">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-purple-600 text-white flex items-center justify-center shadow-xs shrink-0">
              <CalendarClock className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-neutral-950 text-xs">
                  Rollover &amp; Follow-up Queue
                </span>
                <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 border border-purple-200">
                  {rolloverCount} {rolloverCount === 1 ? 'Patient' : 'Patients'}
                </span>
              </div>
              <p className="text-[11px] text-neutral-500 mt-0.5 truncate">
                Postponed report reviews and carryover visits scheduled with priority token prefix (R).
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
            <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-lg bg-white border border-purple-200 text-purple-900 shadow-2xs">
              Priority Review
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
