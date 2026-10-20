export function parseTimeToMinutes(timeStr?: string | null): number | null {
  if (!timeStr) return null;
  const match = timeStr.trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return null;
  let h = parseInt(match[1], 10);
  const m = parseInt(match[2], 10);
  const ampm = match[3].toUpperCase();
  if (ampm === 'PM' && h < 12) h += 12;
  if (ampm === 'AM' && h === 12) h = 0;
  return h * 60 + m;
}

export function toClinicMinutes(isoString: string | null | undefined, clinicTz: string): number {
  if (!isoString || !clinicTz) return 0;
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return 0;
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: clinicTz,
    hour: 'numeric',
    minute: 'numeric',
    hour12: false,
  });
  const parts = formatter.formatToParts(d);
  let h = 0;
  let m = 0;
  for (const part of parts) {
    if (part.type === 'hour') h = parseInt(part.value, 10);
    if (part.type === 'minute') m = parseInt(part.value, 10);
  }
  return h * 60 + m;
}

export function formatClinicTime(isoString: string | null | undefined, clinicTz: string): string {
  if (!isoString || !clinicTz) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-IN', {
    timeZone: clinicTz,
    hour: '2-digit',
    minute: '2-digit',
  });
}
