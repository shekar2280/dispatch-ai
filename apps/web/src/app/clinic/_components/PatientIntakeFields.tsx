import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarDays, X } from 'lucide-react';
import { ClinicCalendarPopover } from './ClinicCalendarPopover';
import { formatDateISO } from '../utils';

export interface IntakeValues {
  name: string;
  phone: string;
  dob: string;
  age: string;
  ageUnit: 'years' | 'months';
  gender?: string;
  bloodGroup?: string;
  address?: string;
}

export function calculateAgeFromDob(dobStr: string): string {
  if (!dobStr) return '';
  const [y, m, d] = dobStr.split('-').map(Number);
  if (!y || !m || !d) return '';
  const birthDate = new Date(y, m - 1, d);
  if (isNaN(birthDate.getTime())) return '';
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const monthDiff = today.getMonth() - birthDate.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
    age--;
  }
  return age >= 0 ? String(age) : '';
}

function formatDobLabel(dob: string): string {
  if (!dob) return '';
  const [y, m, d] = dob.split('-').map(Number);
  if (!y || !m || !d) return dob;
  const date = new Date(y, m - 1, d);
  if (isNaN(date.getTime())) return dob;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function validIntake(value: IntakeValues, requireAge = true) {
  const age = Number(value.age);
  const ageValid = value.age.trim() !== '' && Number.isInteger(age) && age >= 0 && age <= 130;
  return Boolean(value.name.trim() && value.phone.replace(/\D/g, '').length >= 10 && (!requireAge || value.dob || ageValid));
}

interface PatientIntakeFieldsProps {
  value: IntakeValues;
  onChange: (value: IntakeValues) => void;
  requireAge?: boolean;
  compact?: boolean;
}

const inputClass = 'mt-1.5 h-10 w-full rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] px-3 text-xs font-normal text-[#0D2622] outline-none transition-colors placeholder:text-[rgba(13,38,34,0.4)] focus:border-[#0D2622] focus:ring-1 focus:ring-[#0D2622] disabled:bg-[#E3EBE0]/30 disabled:text-[rgba(13,38,34,0.4)] read-only:bg-[#F1F4EE]/60';
const labelClass = 'text-[11px] font-medium text-[#0D2622]';

export default function PatientIntakeFields({ value, onChange, requireAge = true, compact = false }: PatientIntakeFieldsProps) {
  const [calendarOpen, setCalendarOpen] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);
  const todayStr = useMemo(() => formatDateISO(new Date()), []);
  const field = compact ? inputClass.replace('rounded-xl', 'rounded-lg') : inputClass;

  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (value.dob && !value.age) {
      const calculated = calculateAgeFromDob(value.dob);
      if (calculated) {
        onChangeRef.current({ ...value, age: calculated, ageUnit: 'years' });
      }
    }
  }, [value.dob, value.age, value]);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <label className={labelClass}>
        Patient name <span className="text-rose-600">*</span>
        <input aria-label="Patient name" required autoComplete="name" className={field} placeholder="Full name" value={value.name} onChange={event => onChange({ ...value, name: event.target.value })} />
      </label>
      <label className={labelClass}>
        Patient or guardian phone <span className="text-rose-600">*</span>
        <input aria-label="Contact number" type="tel" required autoComplete="tel" className={field} placeholder="Mobile number" value={value.phone} onChange={event => onChange({ ...value, phone: event.target.value })} />
      </label>
      <div className={`relative ${compact ? 'col-span-full' : ''}`}>
        <label className={labelClass}>
          Date of birth
        </label>
        <div className="relative mt-1.5">
          <div
            ref={buttonRef}
            onClick={() => setCalendarOpen(prev => !prev)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setCalendarOpen(prev => !prev);
              }
            }}
            aria-label={`Date of birth: ${value.dob ? formatDobLabel(value.dob) : 'Select date'}`}
            aria-expanded={calendarOpen}
            className={`${field.replace('mt-1.5 ', '')} flex items-center justify-between text-left cursor-pointer select-none`}
          >
            <span className={value.dob ? 'text-[#0D2622] font-normal' : 'text-[rgba(13,38,34,0.4)] font-normal'}>
              {value.dob ? formatDobLabel(value.dob) : 'Select date of birth'}
            </span>
            <div className="flex items-center gap-1 shrink-0 ml-2">
              {value.dob && (
                <button
                  type="button"
                  aria-label="Clear date of birth"
                  onClick={(e) => {
                    e.stopPropagation();
                    onChangeRef.current({ ...value, dob: '', age: '', ageUnit: 'years' });
                  }}
                  className="rounded-md p-1 text-[rgba(13,38,34,0.45)] hover:bg-[#E3EBE0] hover:text-[#0D2622] transition-colors cursor-pointer"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
              <CalendarDays className="h-4 w-4 text-[rgba(13,38,34,0.5)] shrink-0" />
            </div>
          </div>
        </div>
        {calendarOpen && (
          <ClinicCalendarPopover
            anchorRef={buttonRef}
            selectedDate={value.dob || null}
            maxDate={todayStr}
            onSelectDate={(date) => {
              const calculated = calculateAgeFromDob(date);
              onChange({ ...value, dob: date, age: calculated, ageUnit: 'years' });
              setCalendarOpen(false);
            }}
            onClose={() => setCalendarOpen(false)}
            align="left"
          />
        )}
      </div>
      <div className={compact ? 'col-span-full' : ''}>
        <label className={labelClass} htmlFor="patient-reported-age">
          Age {requireAge && !value.dob && <span className="text-rose-600">*</span>}
          {value.dob && <span className="ml-1 text-[10px] font-normal text-[rgba(13,38,34,0.5)]">(calculated)</span>}
        </label>
        <input
          id="patient-reported-age"
          aria-label="Age"
          type="number"
          min="0"
          max="130"
          step="1"
          className={field}
          placeholder={value.dob ? 'Calculated from DOB' : 'Age in years'}
          value={value.age}
          readOnly={Boolean(value.dob)}
          onChange={event => onChange({ ...value, age: event.target.value, ageUnit: 'years' })}
        />
      </div>
      <details className={compact ? "col-span-full border-y border-[rgba(13,38,34,0.08)] py-3" : "col-span-full rounded-xl border border-[rgba(13,38,34,0.14)] bg-[#F1F4EE]/60 px-3 py-2.5"}>
        <summary className="cursor-pointer text-xs font-medium text-[#0D2622]">More patient details <span className="font-normal text-[rgba(13,38,34,0.5)]">(optional)</span></summary>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className={labelClass}>Gender<select aria-label="Gender" className={field} value={value.gender || ''} onChange={event => onChange({ ...value, gender: event.target.value })}><option value="">Not recorded</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option></select></label>
          <label className={labelClass}>Blood group<select aria-label="Blood group" className={field} value={value.bloodGroup || ''} onChange={event => onChange({ ...value, bloodGroup: event.target.value })}><option value="">Unknown</option>{['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map(group => <option key={group} value={group}>{group}</option>)}</select></label>
          <label className={`${labelClass} sm:col-span-2`}>Address<textarea aria-label="Address" autoComplete="street-address" maxLength={500} rows={2} className={`${field} h-auto py-2.5`} placeholder="Street, area, city" value={value.address || ''} onChange={event => onChange({ ...value, address: event.target.value })} /></label>
        </div>
      </details>
    </div>
  );
}
