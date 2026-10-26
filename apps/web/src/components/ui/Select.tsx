'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

const defaultInputCls =
  'h-11 w-full rounded-xl border border-stone-200 bg-stone-50/40 px-3.5 text-sm text-stone-900 shadow-[0_1px_2px_rgba(0,0,0,0.02)] outline-none transition-all placeholder:text-stone-400 focus:bg-white focus:border-stone-900 focus:ring-4 focus:ring-stone-900/5';

export function Select({
  value,
  onChange,
  options,
  id,
  openUpwards,
  className,
  placeholder = 'Select an option',
}: {
  value: string;
  onChange: (val: string) => void;
  options: { value: string; label: string }[];
  id: string;
  openUpwards?: boolean;
  className?: string;
  placeholder?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedOption = options.find((o) => o.value === value);

  return (
    <div className="relative">
      <button
        type="button"
        id={id}
        onClick={() => setIsOpen(!isOpen)}
        onBlur={() => setTimeout(() => setIsOpen(false), 200)}
        className={`${className || defaultInputCls} flex items-center justify-between text-left`}
      >
        <span className={`truncate ${!selectedOption ? 'text-stone-400' : 'text-stone-900'}`}>
          {selectedOption?.label || placeholder}
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-stone-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className={`absolute z-50 w-full max-h-60 overflow-y-auto rounded-xl border border-stone-200 bg-white py-1 shadow-xl ring-1 ring-black/5 animate-in fade-in zoom-in-95 duration-100 scrollbar-thin scrollbar-thumb-stone-200 scrollbar-track-transparent ${openUpwards ? 'bottom-full mb-1.5' : 'top-full mt-1.5'}`}>
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                onChange(opt.value);
                setIsOpen(false);
              }}
              className={`flex w-full items-center px-3.5 py-2 text-xs sm:text-sm text-left transition-colors hover:bg-stone-50 ${
                value === opt.value ? 'bg-stone-100 font-semibold text-stone-900' : 'text-stone-700'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
