'use client';

import { useState } from 'react';
import { CalendarDays, Clock3, Plus, Trash2, ArrowLeft, AlertCircle } from 'lucide-react';
import { ClinicCalendarPopover } from '../../_components/ClinicCalendarPopover';
import { useLeaveCollisionQuery } from '../../_hooks/useClinicQueries';
import { httpClient } from '@/lib/api/httpClient';

export type ChangeKind = 'leave' | 'special_hours' | 'emergency_closure';
export interface ScheduleChange {
  id: string; type: ChangeKind; title: string; startDate: string; endDate: string;
  customHours?: Array<{ name?: string; start: string; end: string }> | null;
  reason?: string | null; emergencyPhone?: string | null; doctorId?: string | null; isApi: boolean;
}
export const fieldClass = 'w-full rounded-xl border border-neutral-300 bg-white px-3 py-2 text-xs text-neutral-900 outline-none focus:border-emerald-700 focus:ring-2 focus:ring-emerald-700/15';
export const buttonClass = 'inline-flex items-center justify-center gap-1.5 rounded-xl border border-neutral-200 bg-white px-3 py-1.5 text-xs font-medium hover:bg-neutral-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700 disabled:opacity-50';
export function dateLabel(date: string) {
  return new Date(`${date}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
}
export function minutes(value: string) {
  const match = value.match(/^(\d{1,2}):(\d{2})(?:\s*(AM|PM))?$/i);
  if (!match) return NaN;
  let h = Number(match[1]);
  if (match[3]) h = h % 12 + (match[3].toUpperCase() === 'PM' ? 12 : 0);
  return h * 60 + Number(match[2]);
}
export function timeLabel(value: string) {
  const n = minutes(value);
  if (!Number.isFinite(n)) return value;
  return `${String(Math.floor(n / 60) % 12 || 12).padStart(2, '0')}:${String(n % 60).padStart(2, '0')} ${n >= 720 ? 'PM' : 'AM'}`;
}
function TimeSelect({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const n = minutes(value); const h = Math.floor(n / 60) % 12 || 12; const m = n % 60; const pm = n >= 720;
  const update = (hour: number, minute: number, period: boolean) => onChange(`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} ${period ? 'PM' : 'AM'}`);
  return <fieldset className="min-w-0"><legend className="mb-1.5 text-xs font-medium text-neutral-500">{label}</legend><div className="flex items-center gap-1 rounded-xl border border-neutral-300 bg-white p-1.5">
    <Clock3 className="ml-1 h-4 w-4 shrink-0 text-neutral-400" />
    <select aria-label={`${label} hour`} value={h} onChange={e => update(+e.target.value, m, pm)} className="min-w-0 flex-1 rounded-lg bg-white py-1.5 text-xs outline-emerald-700">{Array.from({ length: 12 }, (_, i) => i + 1).map(v => <option key={v}>{v}</option>)}</select><span className="text-neutral-400">:</span>
    <select aria-label={`${label} minute`} value={m} onChange={e => update(h, +e.target.value, pm)} className="min-w-0 flex-1 rounded-lg bg-white py-1.5 text-xs outline-emerald-700">{Array.from({ length: 60 }, (_, i) => i).map(v => <option key={v} value={v}>{String(v).padStart(2, '0')}</option>)}</select>
    <select aria-label={`${label} AM or PM`} value={pm ? 'PM' : 'AM'} onChange={e => update(h, m, e.target.value === 'PM')} className="rounded-lg bg-neutral-100 px-1 py-1.5 text-xs font-semibold outline-emerald-700"><option>AM</option><option>PM</option></select>
  </div></fieldset>;
}
function DateField({ label, value, min, onChange }: { label: string; value: string; min: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  return <div className="relative"><span className="mb-1.5 block text-xs font-medium">{label}</span><button aria-label={`${label}: ${dateLabel(value)}`} aria-expanded={open} type="button" className={`${fieldClass} flex items-center justify-between gap-2 text-left`} onClick={() => setOpen(!open)}>{dateLabel(value)}<CalendarDays className="h-4 w-4 shrink-0 text-neutral-400" /></button>{open && <ClinicCalendarPopover selectedDate={value} minDate={min} onSelectDate={d => { onChange(d); setOpen(false); }} onClose={() => setOpen(false)} align="left" />}</div>;
}
export function ScheduleChangeForm({ kind, item, initialDate, today, timezone, orgId, onCancel, onSaved }: {
  kind: ChangeKind; item?: ScheduleChange; initialDate: string; today: string; timezone: string; orgId: string | null; onCancel: () => void; onSaved: (message: string) => void;
}) {
  const special = kind === 'special_hours';
  const [start, setStart] = useState(item?.startDate || initialDate);
  const [end, setEnd] = useState(item?.endDate || initialDate);
  const [title, setTitle] = useState(item?.title || '');
  const [reason, setReason] = useState(item?.reason || '');
  const [phone, setPhone] = useState(item?.emergencyPhone || '');
  const [hours, setHours] = useState(item?.customHours?.length ? item.customHours.map(h => ({ ...h, start: timeLabel(h.start), end: timeLabel(h.end) })) : [{ name: 'Clinic hours', start: '09:00 AM', end: '05:00 PM' }]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const collisions = useLeaveCollisionQuery(orgId, start, end, !special);
  const ordered = [...hours].sort((a, b) => minutes(a.start) - minutes(b.start));
  const invalidHours = special && ordered.some((h, i) => !Number.isFinite(minutes(h.start)) || minutes(h.end) <= minutes(h.start) || (i > 0 && minutes(h.start) < minutes(ordered[i - 1].end)));
  const invalidDates = end < start || (!item && start < today);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy || invalidHours || invalidDates || !orgId || !title.trim()) return;
    setBusy(true); setError('');
    const payload = { title: title.trim(), override_type: special ? 'special_hours' : kind === 'leave' ? 'vacation' : kind, start_date: start, end_date: end, custom_hours: special ? ordered : null, reason: reason.trim() || null, emergency_phone: phone.trim() || null, doctor_id: item?.doctorId || null };
    try {
      const path = `/api/v1/org/${orgId}/closures`;
      if (item) await httpClient.put(`${path}/${item.id}`, payload, { orgId });
      else await httpClient.post(path, payload, { orgId });
      onSaved(`${item ? 'Updated' : 'Saved'} ${title.trim()} · ${dateLabel(start)}${end !== start ? ` – ${dateLabel(end)}` : ''}.`);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save this change. Please try again.'); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save} className="rounded-2xl border border-neutral-200 bg-white shadow-2xs">
    <fieldset disabled={busy} className="min-w-0">
      <div className="border-b border-neutral-100 px-4 py-3.5"><button type="button" onClick={onCancel} className="mb-1.5 flex items-center gap-2 text-xs font-medium text-neutral-500 hover:text-neutral-900"><ArrowLeft className="h-3.5 w-3.5" />All schedule changes</button><h2 className="text-sm font-semibold tracking-tight">{item ? 'Edit' : 'Schedule'} {special ? 'extended hours' : kind === 'leave' ? 'vacation / leave' : 'a closure'}</h2><p className="mt-1 text-xs text-neutral-500">{special ? 'Set custom or extended opening hours for these dates.' : 'Block new bookings during vacations, leaves, or clinic closures.'}</p></div>
      <div className="grid gap-5 p-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-2"><DateField label="Start date" value={start} min={item?.startDate || today} onChange={v => { setStart(v); if (end < v) setEnd(v); }} /><DateField label="End date" value={end} min={start} onChange={setEnd} /></div>
          <label className="block text-xs font-medium">Description<input autoFocus required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} placeholder={special ? 'e.g. Extended evening clinic' : 'e.g. Annual vacation'} className={`${fieldClass} mt-1.5`} /></label>
          {special && <div className="space-y-3"><div><h3 className="text-xs font-semibold">Opening hours</h3><p className="mt-1 text-xs leading-5 text-neutral-500">These hours replace the regular schedule on every selected date. Add separate sessions for breaks.</p></div>{hours.map((h, i) => <div key={i} className="rounded-xl bg-neutral-50 p-3"><div className="mb-1.5 flex items-center justify-between"><span className="text-xs font-medium text-neutral-500">Session {i + 1}</span>{hours.length > 1 && <button type="button" aria-label={`Remove session ${i + 1}`} onClick={() => setHours(hours.filter((_, j) => i !== j))} className="rounded p-1 text-neutral-500 hover:text-rose-700"><Trash2 className="h-4 w-4" /></button>}</div><div className="grid gap-3 sm:grid-cols-2"><TimeSelect label={`Session ${i + 1} opens`} value={h.start} onChange={v => setHours(hours.map((x, j) => j === i ? { ...x, start: v } : x))} /><TimeSelect label={`Session ${i + 1} closes`} value={h.end} onChange={v => setHours(hours.map((x, j) => j === i ? { ...x, end: v } : x))} /></div></div>)}<button type="button" className="flex items-center gap-1 text-xs font-medium text-emerald-800" onClick={() => setHours([...hours, { name: `Session ${hours.length + 1}`, start: '06:00 PM', end: '08:00 PM' }])}><Plus className="h-4 w-4" />Add session</button>{invalidHours && <p role="alert" className="text-xs text-rose-700">Each closing time must be after opening, and sessions must not overlap. Use separate dates for overnight hours.</p>}</div>}
          <label className="block text-xs font-medium">Additional notes <span className="font-normal text-neutral-400">(optional)</span><textarea rows={2} value={reason} onChange={e => setReason(e.target.value)} className={`${fieldClass} mt-1.5`} /></label>
          {!special && <label className="block text-xs font-medium">Emergency contact <span className="font-normal text-neutral-400">(optional)</span><input type="tel" value={phone} onChange={e => setPhone(e.target.value)} placeholder="e.g. +91 98765 43210" className={`${fieldClass} mt-1.5`} /><span className="mt-1.5 block text-xs font-normal text-neutral-500">Shared with callers who need urgent assistance while the clinic is closed.</span></label>}
        </div>
        <aside className="self-start rounded-xl border border-emerald-100 bg-emerald-50/50 p-3.5"><p className="text-xs font-semibold uppercase tracking-wider text-emerald-800">Schedule preview</p><p className="mt-3 text-xs font-semibold">{dateLabel(start)}{end !== start && <><span className="my-1 block text-xs font-normal text-neutral-500">through</span>{dateLabel(end)}</>}</p><div className="my-3 border-t border-emerald-100" />{special ? ordered.map((h, i) => <p key={i} className="mt-1.5 text-xs font-medium tabular-nums">{h.start} – {h.end}</p>) : <p className="text-xs font-semibold">Closed · All day</p>}<p className="mt-3 text-xs leading-5 text-neutral-500">{timezone || 'Loading clinic timezone…'}<br />{special ? 'Applies to each selected date. Regular hours resume afterward.' : 'Regular hours resume after the end date.'}</p>{!special && <div className="mt-3 border-t border-emerald-100 pt-3 text-xs leading-5">{collisions.isFetching ? 'Checking existing appointments…' : collisions.isError ? <span role="alert">Could not check appointments. <button type="button" onClick={() => void collisions.refetch()} className="underline">Retry</button></span> : <>{collisions.data?.count || 0} existing appointments on these dates. {Boolean(collisions.data?.count) && 'These are not moved automatically. Review and reschedule them from the schedule.'}</>}</div>}</aside>
      </div>
      <div className="space-y-3 border-t border-neutral-100 px-4 py-3">{invalidDates && <p role="alert" className="text-xs text-rose-700">Choose a valid date range starting today or later.</p>}{error && <p role="alert" className="flex items-center gap-2 text-xs text-rose-700"><AlertCircle className="h-4 w-4" />{error}</p>}{!orgId && <p role="alert" className="text-xs text-amber-800">Connect a clinic before saving schedule changes.</p>}<div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-neutral-500">After saving, you’ll return to your schedule changes.</p><div className="flex gap-2"><button type="button" onClick={onCancel} className={buttonClass}>Cancel</button><button disabled={busy || invalidHours || invalidDates || !orgId || !timezone || !title.trim() || (!special && (collisions.isFetching || collisions.isError || !collisions.data))} className="rounded-xl bg-emerald-900 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50">{busy ? 'Saving…' : 'Save changes'}</button></div></div></div>
    </fieldset>
  </form>;
}
