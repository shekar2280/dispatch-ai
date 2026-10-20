import type { DaySchedule } from '../app/clinic/types';

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const;

export const DEFAULT_WEEKLY_HOURS: Record<string, DaySchedule> = Object.fromEntries(
  WEEKDAYS.map(day => [day, {
    isOpen: false,
    morningStart: '',
    morningEnd: '',
    eveningStart: '',
    eveningEnd: '',
  }]),
);

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function formatTime(value: unknown): string {
  if (typeof value !== 'string') return '';
  const match = value.trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
  if (!match) return '';
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  const period = match[3]?.toUpperCase();
  if (minute > 59 || hour > (period ? 12 : 23) || (period && hour < 1)) return '';
  return `${String(hour % 12 || 12).padStart(2, '0')}:${match[2]} ${period || (hour >= 12 ? 'PM' : 'AM')}`;
}

export function normalizeWeeklySchedule(raw: unknown): Record<string, DaySchedule> {
  const schedule = asRecord(raw);
  return Object.fromEntries(WEEKDAYS.map(day => {
    const entry = schedule[day] ?? schedule[day.toLowerCase()] ?? schedule[day.toUpperCase()];
    const source = asRecord(entry);
    const windows = Array.isArray(entry) ? entry : Array.isArray(source.windows) ? source.windows : [];
    const morning = asRecord(source.morning);
    const evening = asRecord(source.evening);
    const firstWindow = asRecord(windows[0]);
    const secondWindow = asRecord(windows[1]);
    return [day, {
      isOpen: typeof source.isOpen === 'boolean' ? source.isOpen : Array.isArray(entry) && windows.length > 0,
      morningStart: formatTime(source.morningStart ?? morning.start ?? firstWindow.start),
      morningEnd: formatTime(source.morningEnd ?? morning.end ?? firstWindow.end),
      eveningStart: formatTime(source.eveningStart ?? evening.start ?? secondWindow.start),
      eveningEnd: formatTime(source.eveningEnd ?? evening.end ?? secondWindow.end),
    }];
  }));
}
