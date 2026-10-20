'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { formatDateISO } from '../utils';

interface ClinicCalendarPopoverProps {
  selectedDate?: string | null;
  onSelectDate: (date: string) => void;
  onClose: () => void;
  align?: 'left' | 'right';
  minDate?: string;
}

export function ClinicCalendarPopover({
  selectedDate,
  onSelectDate,
  onClose,
  align = 'right',
  minDate,
}: ClinicCalendarPopoverProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const initialDate = useMemo(() => {
    const fallback = selectedDate || formatDateISO(new Date());
    const target = minDate && fallback < minDate ? minDate : fallback;
    const parsed = new Date(target + 'T00:00:00');
    return isNaN(parsed.getTime()) ? new Date() : parsed;
  }, [selectedDate, minDate]);

  const [viewDate, setViewDate] = useState<Date>(initialDate);

  const todayStr = useMemo(() => formatDateISO(new Date()), []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();

  const monthName = viewDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  const isPrevMonthDisabled = useMemo(() => {
    if (!minDate) return false;
    const [minY, minM] = minDate.split('-').map(Number);
    return year < minY || (year === minY && month <= minM - 1);
  }, [minDate, year, month]);

  const prevMonth = () => {
    if (isPrevMonthDisabled) return;
    setViewDate(new Date(year, month - 1, 1));
  };

  const nextMonth = () => {
    setViewDate(new Date(year, month + 1, 1));
  };

  const calendarDays = useMemo(() => {
    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInCurrentMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();

    const days: Array<{
      dateStr: string;
      dayNumber: number;
      isCurrentMonth: boolean;
      isToday: boolean;
      isSelected: boolean;
      isDisabled: boolean;
    }> = [];

    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const dayNum = daysInPrevMonth - i;
      const d = new Date(year, month - 1, dayNum);
      const iso = formatDateISO(d);
      const disabled = Boolean(minDate && iso < minDate);
      days.push({
        dateStr: iso,
        dayNumber: dayNum,
        isCurrentMonth: false,
        isToday: iso === todayStr,
        isSelected: iso === selectedDate,
        isDisabled: disabled,
      });
    }

    for (let dayNum = 1; dayNum <= daysInCurrentMonth; dayNum++) {
      const d = new Date(year, month, dayNum);
      const iso = formatDateISO(d);
      const disabled = Boolean(minDate && iso < minDate);
      days.push({
        dateStr: iso,
        dayNumber: dayNum,
        isCurrentMonth: true,
        isToday: iso === todayStr,
        isSelected: iso === selectedDate,
        isDisabled: disabled,
      });
    }

    const remainingSlots = 42 - days.length;
    for (let dayNum = 1; dayNum <= remainingSlots; dayNum++) {
      const d = new Date(year, month + 1, dayNum);
      const iso = formatDateISO(d);
      const disabled = Boolean(minDate && iso < minDate);
      days.push({
        dateStr: iso,
        dayNumber: dayNum,
        isCurrentMonth: false,
        isToday: iso === todayStr,
        isSelected: iso === selectedDate,
        isDisabled: disabled,
      });
    }

    return days;
  }, [year, month, todayStr, selectedDate, minDate]);

  const handleSelect = (dateStr: string) => {
    if (minDate && dateStr < minDate) return;
    onSelectDate(dateStr);
    onClose();
  };

  const quickJumpToday = () => {
    const today = new Date();
    const iso = formatDateISO(today);
    if (minDate && iso < minDate) return;
    setViewDate(today);
    handleSelect(iso);
  };

  const quickJumpTomorrow = () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const iso = formatDateISO(tomorrow);
    if (minDate && iso < minDate) return;
    setViewDate(tomorrow);
    handleSelect(iso);
  };

  return (
    <div
      ref={containerRef}
      className={`absolute top-full ${align === 'left' ? 'left-0' : 'right-0'} mt-2 w-[290px] sm:w-[310px] max-w-[calc(100vw-2rem)] bg-[#FFFFFF] border border-[rgba(13,38,34,0.16)] rounded-2xl p-4 shadow-2xl z-[100] text-[#0D2622] font-sans animate-in fade-in zoom-in-95 duration-150`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-[rgba(13,38,34,0.08)]">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-[#0D2622] tracking-tight">
            {monthName}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={prevMonth}
            disabled={isPrevMonthDisabled}
            className={`w-6 h-6 rounded-lg flex items-center justify-center transition-colors ${
              isPrevMonthDisabled
                ? 'text-[rgba(13,38,34,0.2)] cursor-not-allowed opacity-30'
                : 'text-[rgba(13,38,34,0.7)] hover:text-[#0D2622] hover:bg-[#E3EBE0] border border-transparent hover:border-[rgba(13,38,34,0.12)] cursor-pointer'
            }`}
            aria-label="Previous month"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={nextMonth}
            className="w-6 h-6 rounded-lg hover:bg-[#E3EBE0] border border-transparent hover:border-[rgba(13,38,34,0.12)] flex items-center justify-center text-[rgba(13,38,34,0.7)] hover:text-[#0D2622] cursor-pointer transition-colors"
            aria-label="Next month"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="w-6 h-6 ml-1 rounded-lg hover:bg-[#E3EBE0] flex items-center justify-center text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] cursor-pointer transition-colors"
            aria-label="Close"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 pt-3 text-center">
        {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((d) => (
          <span key={d} className="text-[10px] font-bold text-[rgba(13,38,34,0.45)] uppercase tracking-wider py-0.5">
            {d}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1 pt-1">
        {calendarDays.map((day, idx) => {
          if (day.isDisabled) {
            return (
              <div
                key={`${day.dateStr}-${idx}`}
                className="h-8 rounded-lg text-xs flex items-center justify-center text-[rgba(13,38,34,0.2)] bg-transparent cursor-not-allowed opacity-30 select-none"
              >
                <span>{day.dayNumber}</span>
              </div>
            );
          }

          let cellStyle = 'hover:bg-[#E3EBE0] text-[rgba(13,38,34,0.8)] hover:text-[#0D2622]';

          if (!day.isCurrentMonth) {
            cellStyle = 'text-[rgba(13,38,34,0.3)] hover:text-[rgba(13,38,34,0.6)] hover:bg-[#E3EBE0]/50';
          }

          if (day.isToday && !day.isSelected) {
            cellStyle = 'text-[#0D2622] font-bold border border-[rgba(13,38,34,0.16)] bg-[#E3EBE0]/40';
          }

          if (day.isSelected) {
            cellStyle = 'bg-[#0D2622] text-[#F1F4EE] font-bold shadow-xs hover:bg-[#143530]';
          }

          return (
            <button
              key={`${day.dateStr}-${idx}`}
              type="button"
              aria-label={day.dateStr}
              onClick={() => handleSelect(day.dateStr)}
              className={`h-8 rounded-lg text-xs flex items-center justify-center cursor-pointer transition-all ${cellStyle}`}
            >
              <span>{day.dayNumber}</span>
            </button>
          );
        })}
      </div>

      <div className="pt-3 mt-3 border-t border-[rgba(13,38,34,0.08)] flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5">
          {(!minDate || todayStr >= minDate) && (
            <button
              type="button"
              onClick={quickJumpToday}
              className="px-2 py-1 rounded-md text-[11px] font-bold bg-[#E3EBE0]/60 hover:bg-[#E3EBE0] border border-[rgba(13,38,34,0.14)] text-[#0D2622] transition-colors cursor-pointer"
            >
              Today
            </button>
          )}
          <button
            type="button"
            onClick={quickJumpTomorrow}
            className="px-2 py-1 rounded-md text-[11px] font-bold bg-[#E3EBE0]/60 hover:bg-[#E3EBE0] border border-[rgba(13,38,34,0.14)] text-[#0D2622] transition-colors cursor-pointer"
          >
            Tomorrow
          </button>
        </div>

        {selectedDate && (
          <span className="text-[10px] font-semibold text-[rgba(13,38,34,0.5)] font-mono">
            {selectedDate}
          </span>
        )}
      </div>
    </div>
  );
}
