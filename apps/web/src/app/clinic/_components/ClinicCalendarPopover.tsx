'use client';

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { formatDateISO } from '../utils';

interface ClinicCalendarPopoverProps {
  selectedDate?: string | null;
  onSelectDate: (date: string) => void;
  onClose: () => void;
  align?: 'left' | 'right';
  minDate?: string;
  maxDate?: string;
  anchorRef?: React.RefObject<HTMLElement | null>;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export function ClinicCalendarPopover({
  selectedDate,
  onSelectDate,
  onClose,
  align = 'right',
  minDate,
  maxDate,
  anchorRef,
}: ClinicCalendarPopoverProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const markerRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const initialDate = useMemo(() => {
    const fallback = selectedDate || formatDateISO(new Date());
    let target = minDate && fallback < minDate ? minDate : fallback;
    if (maxDate && target > maxDate) target = maxDate;
    const parsed = new Date(target + 'T00:00:00');
    return isNaN(parsed.getTime()) ? new Date() : parsed;
  }, [selectedDate, minDate, maxDate]);

  const [viewDate, setViewDate] = useState<Date>(initialDate);

  const todayStr = useMemo(() => formatDateISO(new Date()), []);
  const tomorrowStr = useMemo(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return formatDateISO(tomorrow);
  }, []);

  const calculatePosition = useCallback(() => {
    const anchor = anchorRef?.current || markerRef.current?.parentElement;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const popoverWidth = 310;
    const popoverHeight = 356;
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;

    let top = rect.bottom + 6;
    if (spaceBelow < popoverHeight && spaceAbove > spaceBelow) {
      top = Math.max(8, rect.top - popoverHeight - 6);
    } else if (top + popoverHeight > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - popoverHeight - 8);
    }

    let left = align === 'right' ? rect.right - popoverWidth : rect.left;
    if (left + popoverWidth > window.innerWidth - 12) {
      left = window.innerWidth - popoverWidth - 12;
    }
    if (left < 12) {
      left = 12;
    }

    setCoords({ top, left });
  }, [align, anchorRef]);

  useEffect(() => {
    setMounted(true);
    calculatePosition();
  }, [calculatePosition]);

  useEffect(() => {
    if (!mounted) return;
    calculatePosition();
    window.addEventListener('resize', calculatePosition);
    window.addEventListener('scroll', calculatePosition, true);
    return () => {
      window.removeEventListener('resize', calculatePosition);
      window.removeEventListener('scroll', calculatePosition, true);
    };
  }, [mounted, calculatePosition]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      const anchor = anchorRef?.current || markerRef.current?.parentElement;
      if (
        containerRef.current &&
        !containerRef.current.contains(target) &&
        (!anchor || !anchor.contains(target))
      ) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose, anchorRef]);

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();

  const isPrevMonthDisabled = useMemo(() => {
    if (!minDate) return false;
    const [minY, minM] = minDate.split('-').map(Number);
    return year < minY || (year === minY && month <= minM - 1);
  }, [minDate, year, month]);

  const isNextMonthDisabled = useMemo(() => {
    if (!maxDate) return false;
    const [maxY, maxM] = maxDate.split('-').map(Number);
    return year > maxY || (year === maxY && month >= maxM - 1);
  }, [maxDate, year, month]);

  const prevMonth = () => {
    if (isPrevMonthDisabled) return;
    setViewDate(new Date(year, month - 1, 1));
  };

  const nextMonth = () => {
    if (isNextMonthDisabled) return;
    setViewDate(new Date(year, month + 1, 1));
  };

  const years = useMemo(() => {
    const currentYear = new Date().getFullYear();
    const minYear = minDate ? Number(minDate.split('-')[0]) : 1920;
    const maxYear = maxDate ? Number(maxDate.split('-')[0]) : currentYear + 5;
    const list: number[] = [];
    for (let y = maxYear; y >= minYear; y--) {
      list.push(y);
    }
    return list;
  }, [minDate, maxDate]);

  const calendarDays = useMemo(() => {
    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInCurrentMonth = new Date(year, month + 1, 0).getDate();

    const days: Array<{
      dateStr: string;
      dayNumber: number;
      isToday: boolean;
      isSelected: boolean;
      isDisabled: boolean;
    } | null> = [];

    for (let i = 0; i < firstDayIndex; i++) {
      days.push(null);
    }

    for (let dayNum = 1; dayNum <= daysInCurrentMonth; dayNum++) {
      const d = new Date(year, month, dayNum);
      const iso = formatDateISO(d);
      const disabled = Boolean((minDate && iso < minDate) || (maxDate && iso > maxDate));
      days.push({
        dateStr: iso,
        dayNumber: dayNum,
        isToday: iso === todayStr,
        isSelected: iso === selectedDate,
        isDisabled: disabled,
      });
    }

    while (days.length % 7 !== 0) {
      days.push(null);
    }

    return days;
  }, [year, month, todayStr, selectedDate, minDate, maxDate]);

  const handleSelect = (dateStr: string) => {
    if (minDate && dateStr < minDate) return;
    if (maxDate && dateStr > maxDate) return;
    onSelectDate(dateStr);
    onClose();
  };

  const quickJumpToday = () => {
    const today = new Date();
    const iso = formatDateISO(today);
    if (minDate && iso < minDate) return;
    if (maxDate && iso > maxDate) return;
    setViewDate(today);
    handleSelect(iso);
  };

  const quickJumpTomorrow = () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const iso = formatDateISO(tomorrow);
    if (minDate && iso < minDate) return;
    if (maxDate && iso > maxDate) return;
    setViewDate(tomorrow);
    handleSelect(iso);
  };

  const popoverContent = (
    <div
      ref={containerRef}
      style={{ top: `${coords.top}px`, left: `${coords.left}px` }}
      className="fixed z-[9999] w-[310px] max-w-[calc(100vw-2rem)] bg-[#FFFFFF] border border-[rgba(13,38,34,0.16)] rounded-2xl p-4 shadow-2xl text-[#0D2622] font-sans animate-in fade-in zoom-in-95 duration-150 select-none"
    >
      <div className="flex items-center justify-between pb-3 border-b border-[rgba(13,38,34,0.08)]">
        <div className="flex items-center gap-1">
          <select
            aria-label="Select month"
            value={month}
            onChange={(e) => setViewDate(new Date(year, Number(e.target.value), 1))}
            className="text-xs font-medium text-[#0D2622] bg-transparent outline-none cursor-pointer hover:bg-[#E3EBE0] rounded px-1 py-0.5 transition-colors border border-transparent hover:border-[rgba(13,38,34,0.12)]"
          >
            {MONTH_NAMES.map((name, idx) => (
              <option key={name} value={idx}>{name}</option>
            ))}
          </select>
          <select
            aria-label="Select year"
            value={year}
            onChange={(e) => setViewDate(new Date(Number(e.target.value), month, 1))}
            className="text-xs font-medium text-[#0D2622] bg-transparent outline-none cursor-pointer hover:bg-[#E3EBE0] rounded px-1 py-0.5 transition-colors border border-transparent hover:border-[rgba(13,38,34,0.12)]"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
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
            disabled={isNextMonthDisabled}
            className={`w-6 h-6 rounded-lg flex items-center justify-center transition-colors ${
              isNextMonthDisabled
                ? 'text-[rgba(13,38,34,0.2)] cursor-not-allowed opacity-30'
                : 'text-[rgba(13,38,34,0.7)] hover:text-[#0D2622] hover:bg-[#E3EBE0] border border-transparent hover:border-[rgba(13,38,34,0.12)] cursor-pointer'
            }`}
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
          <span key={d} className="text-[10px] font-medium text-[rgba(13,38,34,0.45)] uppercase tracking-wider py-0.5">
            {d}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1 pt-1">
        {calendarDays.map((day, idx) => {
          if (!day) {
            return (
              <div
                key={`blank-${idx}`}
                className="h-8 select-none"
              />
            );
          }

          if (day.isDisabled) {
            return (
              <div
                key={day.dateStr}
                className="h-8 rounded-lg text-xs flex items-center justify-center text-[rgba(13,38,34,0.2)] bg-transparent cursor-not-allowed opacity-30 select-none"
              >
                <span>{day.dayNumber}</span>
              </div>
            );
          }

          let cellStyle = 'hover:bg-[#E3EBE0] text-[rgba(13,38,34,0.8)] hover:text-[#0D2622]';

          if (day.isToday && !day.isSelected) {
            cellStyle = 'text-[#0D2622] font-semibold border border-[rgba(13,38,34,0.16)] bg-[#E3EBE0]/40';
          }

          if (day.isSelected) {
            cellStyle = 'bg-[#0D2622] text-[#F1F4EE] font-medium shadow-xs hover:bg-[#143530]';
          }

          return (
            <button
              key={day.dateStr}
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
          {(!minDate || todayStr >= minDate) && (!maxDate || todayStr <= maxDate) && (
            <button
              type="button"
              onClick={quickJumpToday}
              className="px-2 py-1 rounded-md text-[11px] font-medium bg-[#E3EBE0]/60 hover:bg-[#E3EBE0] border border-[rgba(13,38,34,0.14)] text-[#0D2622] transition-colors cursor-pointer"
            >
              Today
            </button>
          )}
          {(!minDate || tomorrowStr >= minDate) && (!maxDate || tomorrowStr <= maxDate) && (
            <button
              type="button"
              onClick={quickJumpTomorrow}
              className="px-2 py-1 rounded-md text-[11px] font-medium bg-[#E3EBE0]/60 hover:bg-[#E3EBE0] border border-[rgba(13,38,34,0.14)] text-[#0D2622] transition-colors cursor-pointer"
            >
              Tomorrow
            </button>
          )}
        </div>

        {selectedDate && (
          <span className="text-[10px] font-medium text-[rgba(13,38,34,0.5)] font-mono">
            {selectedDate}
          </span>
        )}
      </div>
    </div>
  );

  return (
    <>
      <div ref={markerRef} className="hidden" />
      {mounted && typeof document !== 'undefined' && createPortal(popoverContent, document.body)}
    </>
  );
}
