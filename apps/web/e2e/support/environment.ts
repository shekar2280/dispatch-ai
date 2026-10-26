import { randomUUID } from 'node:crypto';

export const apiBase = (process.env.E2E_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing ${name}. Configure real staging data; this suite never skips missing prerequisites.`);
  return value;
}

export function syntheticPatient() {
  const suffix = randomUUID().replaceAll('-', '').slice(0, 16);
  return { name: `E2E${suffix} Patient`, phone: required('E2E_PATIENT_PHONE'), age: '30', marker: suffix };
}

export function clinicDate(timezone: string, offset = 0): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const field = (type: string) => parts.find(part => part.type === type)!.value;
  const date = new Date(`${field('year')}-${field('month')}-${field('day')}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}
