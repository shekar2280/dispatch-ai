'use client';

import React, { useState, useMemo } from 'react';
import { RotateCcw, Calendar, X } from 'lucide-react';
import { ClinicCalendarPopover } from '../../_components/ClinicCalendarPopover';
import { formatDateISO } from '../../utils';

interface CallsHeaderProps {
  isLoading: boolean;
  isRevalidating: boolean;
  onRefresh: () => void;
  selectedDate: string | null;
  onDateChange: (date: string | null) => void;
}

export function CallsHeader({
  isLoading,
  isRevalidating,
  onRefresh,
  selectedDate,
  onDateChange,
}: CallsHeaderProps) {
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);

  const todayStr = useMemo(() => formatDateISO(new Date()), []);

  const dateLabel = useMemo(() => {
    if (!selectedDate) return 'All Dates';
    const target = new Date(selectedDate + 'T00:00:00');
    if (selectedDate === todayStr)
      return `Today, ${target.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}`;
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    if (selectedDate === formatDateISO(yesterday)) return 'Yesterday';
    return target.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  }, [selectedDate, todayStr]);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-neutral-200/80">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold tracking-tight text-neutral-950">
            Call History
          </h1>
        </div>
        <p className="text-xs text-neutral-500 mt-0.5">
          Incoming patient calls and appointments handled by Tulsi.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap self-start sm:self-auto">
        <div className="flex items-center bg-white border border-neutral-200 rounded-xl p-0.5 shadow-2xs">
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsCalendarOpen((prev) => !prev)}
              className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer ${
                selectedDate
                  ? 'text-neutral-950 bg-neutral-100/80 hover:bg-neutral-100'
                  : 'text-neutral-700 hover:text-black hover:bg-neutral-50'
              }`}
            >
              <Calendar className="w-3.5 h-3.5 text-neutral-400" />
              <span>{dateLabel}</span>
            </button>

            {isCalendarOpen && (
              <ClinicCalendarPopover
                selectedDate={selectedDate}
                onSelectDate={(d) => {
                  onDateChange(d);
                  setIsCalendarOpen(false);
                }}
                onClose={() => setIsCalendarOpen(false)}
                align="right"
              />
            )}
          </div>

          {selectedDate && (
            <button
              type="button"
              onClick={() => {
                onDateChange(null);
                setIsCalendarOpen(false);
              }}
              className="p-1 text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 rounded-md transition-colors cursor-pointer"
              title="Clear date filter"
              aria-label="Clear date filter"
            >
              <X className="w-3 h-3" />
            </button>
          )}

          {selectedDate !== todayStr && (
            <button
              type="button"
              onClick={() => {
                onDateChange(todayStr);
                setIsCalendarOpen(false);
              }}
              className="px-2 py-1 text-[11px] font-semibold text-neutral-500 hover:text-black hover:bg-neutral-50 rounded-lg transition-colors cursor-pointer"
            >
              Today
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading || isRevalidating}
          title="Refresh"
          aria-label="Refresh"
          className="inline-flex items-center justify-center p-2 rounded-xl bg-white border border-neutral-200 shadow-2xs text-neutral-700 hover:bg-neutral-50 hover:text-neutral-900 active:scale-[0.98] transition-all disabled:opacity-50 cursor-pointer"
        >
          <RotateCcw
            className={`w-3.5 h-3.5 text-neutral-500 ${isLoading || isRevalidating ? 'animate-spin' : ''}`}
          />
        </button>
      </div>
    </div>
  );
}
