import React, { useEffect, useState } from 'react';

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

export function validIntake(value: IntakeValues, requireAge = true) {
  const age = Number(value.age);
  const ageValid = value.age.trim() !== '' && Number.isInteger(age) && age >= 0 && age <= (value.ageUnit === 'months' ? 1560 : 130);
  return Boolean(value.name.trim() && value.phone.replace(/\D/g, '').length >= 10 && (!requireAge || value.dob || ageValid));
}

interface PatientIntakeFieldsProps {
  value: IntakeValues;
  onChange: (value: IntakeValues) => void;
  requireAge?: boolean;
  compact?: boolean;
}

const inputClass = 'mt-1.5 h-10 w-full rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] px-3 text-xs font-semibold text-[#0D2622] outline-none transition-colors placeholder:text-[rgba(13,38,34,0.4)] focus:border-[#0D2622] focus:ring-1 focus:ring-[#0D2622] disabled:bg-[#E3EBE0]/30 disabled:text-[rgba(13,38,34,0.4)]';
const labelClass = 'text-[11px] font-bold text-[#0D2622]';

export default function PatientIntakeFields({ value, onChange, requireAge = true, compact = false }: PatientIntakeFieldsProps) {
  const [useDob, setUseDob] = useState(Boolean(value.dob));
  useEffect(() => { if (value.dob) setUseDob(true); else if (value.age) setUseDob(false); }, [value.dob, value.age]);
  const field = compact ? inputClass.replace('rounded-xl', 'rounded-lg') : inputClass;
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
      {compact && <div className="col-span-full flex items-center gap-4 border-t border-[rgba(13,38,34,0.08)] pt-3">
        <span className="text-[11px] font-bold text-[#0D2622]">Age / birth date</span>
        <div className="ml-auto flex gap-3">{[false, true].map(dob => <button type="button" key={String(dob)} aria-pressed={useDob === dob} onClick={() => { if (useDob === dob) return; setUseDob(dob); onChange({ ...value, dob: '', age: '' }); }} className={`border-b pb-1 text-[11px] font-bold ${useDob === dob ? 'border-[#0D2622] text-[#0D2622]' : 'border-transparent text-[rgba(13,38,34,0.5)]'}`}>{dob ? 'Date of birth' : 'Age'}</button>)}</div>
      </div>}
      {(!compact || useDob) && <label className={`${labelClass} ${compact ? 'col-span-full' : ''}`}>
        Date of birth
        <input aria-label="Date of birth" type="date" className={field} value={value.dob} onChange={event => onChange({ ...value, dob: event.target.value, age: '' })} />
      </label>}
      {(!compact || !useDob) && <div className={compact ? 'col-span-full' : ''}>
        <label className={labelClass} htmlFor="patient-reported-age">{compact ? 'Age' : 'Or age'} {requireAge && !value.dob && <span className="text-rose-600">*</span>}</label>
        <div className="mt-1.5 flex gap-2">
          <input id="patient-reported-age" aria-label="Age" type="number" min="0" max={value.ageUnit === 'months' ? 1560 : 130} step="1" className={`${field.replace('mt-1.5 ', '')} min-w-0 flex-1`} placeholder="Age" value={value.age} disabled={Boolean(value.dob)} onChange={event => onChange({ ...value, age: event.target.value })} />
          <select aria-label="Age unit" className="h-10 rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] px-2 text-xs font-semibold text-[#0D2622] outline-none focus:border-[#0D2622]" value={value.ageUnit} disabled={Boolean(value.dob)} onChange={event => onChange({ ...value, ageUnit: event.target.value as IntakeValues['ageUnit'] })}>
            <option value="years">Years</option>
            <option value="months">Months</option>
          </select>
        </div>
      </div>}
      <details className={compact ? "col-span-full border-y border-[rgba(13,38,34,0.08)] py-3" : "col-span-full rounded-xl border border-[rgba(13,38,34,0.14)] bg-[#F1F4EE]/60 px-3 py-2.5"}>
        <summary className="cursor-pointer text-xs font-bold text-[#0D2622]">More patient details <span className="font-normal text-[rgba(13,38,34,0.5)]">(optional)</span></summary>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className={labelClass}>Gender<select aria-label="Gender" className={field} value={value.gender || ''} onChange={event => onChange({ ...value, gender: event.target.value })}><option value="">Not recorded</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option></select></label>
          <label className={labelClass}>Blood group<select aria-label="Blood group" className={field} value={value.bloodGroup || ''} onChange={event => onChange({ ...value, bloodGroup: event.target.value })}><option value="">Unknown</option>{['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map(group => <option key={group} value={group}>{group}</option>)}</select></label>
          <label className={`${labelClass} sm:col-span-2`}>Address<textarea aria-label="Address" autoComplete="street-address" maxLength={500} rows={2} className={`${field} h-auto py-2.5`} placeholder="Street, area, city" value={value.address || ''} onChange={event => onChange({ ...value, address: event.target.value })} /></label>
        </div>
      </details>
    </div>
  );
}
