'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Clock, Check } from 'lucide-react';

interface TimePickerProps {
  value?: string;
  onChange: (val: string) => void;
  align?: 'left' | 'right';
}

export function TimePicker({ value = '10:00 AM', onChange, align }: TimePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<'hour' | 'minute'>('hour');
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const parseTime = (str?: string) => {
    if (!str || typeof str !== 'string') {
      return { hour: 10, minute: 0, ampm: 'AM' };
    }
    const match = str.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
    if (!match) return { hour: 10, minute: 0, ampm: 'AM' };
    return {
      hour: parseInt(match[1], 10),
      minute: (Math.round(parseInt(match[2], 10) / 5) * 5) % 60,
      ampm: match[3].toUpperCase(),
    };
  };

  const { hour, minute, ampm } = parseTime(value);

  const update = (h: number, m: number, ap: string) => {
    const formattedHour = h.toString().padStart(2, '0');
    const formattedMin = m.toString().padStart(2, '0');
    onChange(`${formattedHour}:${formattedMin} ${ap}`);
  };

  const calculatePosition = useCallback(() => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const popoverWidth = 256;
    const popoverHeight = 310;
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;

    let top = rect.bottom + 6;
    if (spaceBelow < popoverHeight && spaceAbove > spaceBelow) {
      top = Math.max(8, rect.top - popoverHeight - 6);
    }

    let left = align === 'right' ? rect.right - popoverWidth : rect.left;
    if (left + popoverWidth > window.innerWidth - 12) {
      left = window.innerWidth - popoverWidth - 12;
    }
    if (left < 12) {
      left = 12;
    }

    setCoords({ top, left });
  }, [align]);

  const toggleOpen = () => {
    if (!isOpen) {
      calculatePosition();
      setMode('hour');
    }
    setIsOpen((prev) => !prev);
  };

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        buttonRef.current &&
        !buttonRef.current.contains(target) &&
        popoverRef.current &&
        !popoverRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    const handleScrollOrResize = () => {
      calculatePosition();
    };

    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('resize', handleScrollOrResize);
    window.addEventListener('scroll', handleScrollOrResize, true);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('resize', handleScrollOrResize);
      window.removeEventListener('scroll', handleScrollOrResize, true);
    };
  }, [isOpen, calculatePosition]);

  const hoursPositions = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  const minutesPositions = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];

  const dialRadius = 66;
  const dialCenter = 90;

  const currentAngle = mode === 'hour'
    ? (hour % 12) * 30
    : (minute / 5) * 30;

  const handRad = (currentAngle * Math.PI) / 180;
  const handX = dialCenter + dialRadius * Math.sin(handRad);
  const handY = dialCenter - dialRadius * Math.cos(handRad);

  const handleDialClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - dialCenter;
    const y = e.clientY - rect.top - dialCenter;
    const dist = Math.sqrt(x * x + y * y);
    if (dist < 15) return;

    let rad = Math.atan2(x, -y);
    if (rad < 0) rad += 2 * Math.PI;
    const deg = (rad * 180) / Math.PI;

    if (mode === 'hour') {
      let rawHour = Math.round(deg / 30);
      if (rawHour === 0) rawHour = 12;
      update(rawHour, minute, ampm);
      setMode('minute');
    } else {
      let rawMin = (Math.round(deg / 30) * 5) % 60;
      update(hour, rawMin, ampm);
    }
  };

  return (
    <div ref={containerRef} className="relative inline-block text-left select-none">
      <button
        ref={buttonRef}
        type="button"
        onClick={toggleOpen}
        className={`w-[92px] h-7 px-2 bg-white border rounded-lg text-xs font-bold text-neutral-900 flex items-center justify-between transition-all shadow-2xs cursor-pointer ${
          isOpen ? 'border-neutral-950 ring-1 ring-neutral-950/10' : 'border-neutral-200 hover:border-neutral-900'
        }`}
      >
        <span className="text-[11.5px] font-bold text-neutral-900">{value}</span>
        <Clock className={`w-3 h-3 ${isOpen ? 'text-neutral-950' : 'text-neutral-400'}`} />
      </button>

      {isOpen &&
        mounted &&
        createPortal(
          <div
            ref={popoverRef}
            style={{ top: `${coords.top}px`, left: `${coords.left}px` }}
            className="fixed z-[9999] w-[256px] p-3 bg-white rounded-2xl shadow-2xl border border-neutral-200 space-y-2.5 animate-in fade-in zoom-in-95 duration-150"
          >
            <div className="flex items-center justify-between pb-2 border-b border-neutral-100">
              <div className="flex items-center bg-[#FBF9F5] border border-[#ECE7DE] p-0.5 rounded-xl shadow-2xs">
                <button
                  type="button"
                  onClick={() => setMode('hour')}
                  className={`px-2 py-0.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                    mode === 'hour'
                      ? 'bg-black text-[#DFD0B8] shadow-xs'
                      : 'text-neutral-600 hover:text-black hover:bg-neutral-200/50'
                  }`}
                >
                  {hour.toString().padStart(2, '0')}
                </button>
                <span className="text-xs font-bold text-neutral-300 px-0.5">:</span>
                <button
                  type="button"
                  onClick={() => setMode('minute')}
                  className={`px-2 py-0.5 text-xs font-bold rounded-lg transition-all cursor-pointer font-mono ${
                    mode === 'minute'
                      ? 'bg-black text-[#DFD0B8] shadow-xs'
                      : 'text-neutral-600 hover:text-black hover:bg-neutral-200/50'
                  }`}
                >
                  {minute.toString().padStart(2, '0')}
                </button>
              </div>

              <div className="flex items-center p-0.5 bg-neutral-100 rounded-xl gap-0.5 border border-neutral-200/60">
                {(['AM', 'PM'] as const).map((period) => (
                  <button
                    key={period}
                    type="button"
                    onClick={() => update(hour, minute, period)}
                    className={`px-2 py-0.5 text-[10.5px] font-bold rounded-lg transition-all cursor-pointer ${
                      ampm === period
                        ? 'bg-black text-[#DFD0B8] shadow-xs'
                        : 'text-neutral-500 hover:text-black'
                    }`}
                  >
                    {period}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between px-0.5">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-neutral-400">
                {mode === 'hour' ? 'Select Hour' : 'Select Minute'}
              </span>
              <div className="flex items-center gap-1.5 text-[10.5px] font-semibold text-neutral-500">
                <button
                  type="button"
                  onClick={() => setMode('hour')}
                  className={`px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
                    mode === 'hour' ? 'text-black font-bold' : 'hover:text-black'
                  }`}
                >
                  Hours
                </button>
                <span className="text-neutral-300">•</span>
                <button
                  type="button"
                  onClick={() => setMode('minute')}
                  className={`px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
                    mode === 'minute' ? 'text-black font-bold' : 'hover:text-black'
                  }`}
                >
                  Minutes
                </button>
              </div>
            </div>

            <div
              onClick={handleDialClick}
              className="w-[180px] h-[180px] rounded-full bg-[#FBF9F5] border border-[#ECE7DE] relative mx-auto shadow-inner cursor-pointer"
            >
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-[168px] h-[168px] rounded-full border border-dashed border-neutral-200/70" />
              </div>

              <svg
                className="absolute inset-0 pointer-events-none transition-all duration-150 ease-out"
                width="180"
                height="180"
                viewBox="0 0 180 180"
              >
                <line
                  x1={dialCenter}
                  y1={dialCenter}
                  x2={handX}
                  y2={handY}
                  stroke="#09090b"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <circle cx={dialCenter} cy={dialCenter} r="3.5" fill="#09090b" />
                <circle cx={handX} cy={handY} r="13" fill="#09090b" />
              </svg>

              {mode === 'hour' &&
                hoursPositions.map((h, idx) => {
                  const angle = idx * 30;
                  const rad = (angle * Math.PI) / 180;
                  const x = dialCenter + dialRadius * Math.sin(rad) - 13;
                  const y = dialCenter - dialRadius * Math.cos(rad) - 13;
                  const isSelected = hour === h;

                  return (
                    <button
                      key={h}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        update(h, minute, ampm);
                        setMode('minute');
                      }}
                      style={{ left: `${x}px`, top: `${y}px` }}
                      className={`absolute w-[26px] h-[26px] rounded-full flex items-center justify-center text-[11px] font-bold transition-all cursor-pointer z-10 ${
                        isSelected
                          ? 'text-[#DFD0B8] scale-105'
                          : 'text-neutral-700 hover:text-black hover:bg-neutral-200/60'
                      }`}
                    >
                      {h}
                    </button>
                  );
                })}

              {mode === 'minute' &&
                minutesPositions.map((m, idx) => {
                  const angle = idx * 30;
                  const rad = (angle * Math.PI) / 180;
                  const x = dialCenter + dialRadius * Math.sin(rad) - 13;
                  const y = dialCenter - dialRadius * Math.cos(rad) - 13;
                  const isSelected = minute === m;

                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        update(hour, m, ampm);
                      }}
                      style={{ left: `${x}px`, top: `${y}px` }}
                      className={`absolute w-[26px] h-[26px] rounded-full flex items-center justify-center text-[10.5px] font-mono font-bold transition-all cursor-pointer z-10 ${
                        isSelected
                          ? 'text-[#DFD0B8] scale-105'
                          : 'text-neutral-700 hover:text-black hover:bg-neutral-200/60'
                      }`}
                    >
                      {m.toString().padStart(2, '0')}
                    </button>
                  );
                })}
            </div>

            <div className="pt-2 border-t border-neutral-100 flex items-center justify-between">
              <div className="flex items-center gap-1">
                {[
                  { label: '9 AM', h: 9, m: 0, ap: 'AM' },
                  { label: '1 PM', h: 1, m: 0, ap: 'PM' },
                  { label: '5 PM', h: 5, m: 0, ap: 'PM' },
                ].map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => update(preset.h, preset.m, preset.ap)}
                    className="px-1.5 py-0.5 text-[9.5px] font-semibold text-neutral-500 bg-[#FBF9F5] border border-[#ECE7DE] rounded hover:border-neutral-400 hover:text-black transition-colors cursor-pointer"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="px-2.5 py-1 bg-black text-white hover:bg-neutral-800 text-[11px] font-semibold rounded-lg shadow-2xs transition-colors cursor-pointer flex items-center gap-1"
              >
                <Check className="w-3 h-3 text-[#DFD0B8]" />
                <span>Done</span>
              </button>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
