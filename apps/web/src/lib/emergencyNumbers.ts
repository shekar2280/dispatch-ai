import emergencyData from '../data/emergency_numbers.json';

interface EmergencyEntry {
  ambulance?: string;
  police?: string;
  fire?: string;
}

const table = emergencyData as Record<string, EmergencyEntry>;

export function getEmergencyNumberByCountry(countryCode: string): string {
  const code = (countryCode || '').trim().toUpperCase();
  const entry = table[code];
  if (!entry) return '';
  return entry.ambulance || entry.police || entry.fire || '';
}
