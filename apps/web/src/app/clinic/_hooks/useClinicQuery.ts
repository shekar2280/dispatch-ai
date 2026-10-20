'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createClient } from '@/lib/supabase/client';
import {
  DEFAULT_CLINIC_PROFILE,
  DEFAULT_WEEKLY_HOURS,
  DaySchedule,
  normalizeVoicePersona,
} from '../constants';
import { API_ROUTES } from '@/lib/constants';
import { useClinicStore } from '../store';
import { httpClient } from '@/lib/api/httpClient';
import { getEmergencyNumberByCountry } from '@/lib/emergencyNumbers';
import { normalizeWeeklySchedule } from '@/lib/weekly-schedule';

export { normalizeWeeklySchedule } from '@/lib/weekly-schedule';

export interface ClinicSettingsData {
  orgId: string;
  clinicName: string;
  doctorName: string;
  doctorEmail: string;
  doctorPhone: string;
  specialty: string;
  consultationFee: string;
  countryCode: string;
  currencyCode: string;
  currencySymbol: string;
  city: string;
  clinicAddress: string;
  timezone: string;
  emergencyPhone: string;
  slotDuration: string;
  slotBuffer: string;
  maxDailyPatients: string;
  weeklyHours: Record<string, DaySchedule>;
  greetingPrompt: string;
  voicePersona: string;
  languageMode: string;
}

export function mapClinicSettings(userRow: any, email = ''): ClinicSettingsData {
  const targetOrgId = userRow.org_id;
  const defaultData: ClinicSettingsData = {
    orgId: targetOrgId,
    clinicName: DEFAULT_CLINIC_PROFILE.clinicName,
    doctorName: DEFAULT_CLINIC_PROFILE.doctorName,
    doctorEmail: DEFAULT_CLINIC_PROFILE.doctorEmail,
    doctorPhone: DEFAULT_CLINIC_PROFILE.doctorPhone,
    specialty: DEFAULT_CLINIC_PROFILE.specialty,
    consultationFee: DEFAULT_CLINIC_PROFILE.consultationFee,
    countryCode: '',
    currencyCode: '',
    currencySymbol: '',
    city: DEFAULT_CLINIC_PROFILE.city || '',
    clinicAddress: DEFAULT_CLINIC_PROFILE.clinicAddress || '',
    timezone: '',
    emergencyPhone: DEFAULT_CLINIC_PROFILE.emergencyPhone,
    slotDuration: '',
    slotBuffer: '',
    maxDailyPatients: '',
    weeklyHours: DEFAULT_WEEKLY_HOURS,
    greetingPrompt: DEFAULT_CLINIC_PROFILE.defaultGreetingPrompt,
    voicePersona: 'priya',
    languageMode: 'en_hi_bilingual',
  };

  defaultData.doctorEmail = email;
  {
    if (userRow?.org_id) {
      defaultData.orgId = targetOrgId;
    }
    if (userRow?.organizations) {
      const org = userRow.organizations as any;
      const booking = org.booking_settings || {};
      const voiceAi = org.voice_ai_settings || {};
      if (org.name) defaultData.clinicName = org.name;
      if (voiceAi.lead_doctor_name || org.lead_doctor_name) {
        defaultData.doctorName = voiceAi.lead_doctor_name || org.lead_doctor_name;
      } else if (userRow.full_name) {
        defaultData.doctorName = userRow.full_name;
      }
      if (voiceAi.clinic_specialty || org.clinic_specialty) {
        defaultData.specialty = voiceAi.clinic_specialty || org.clinic_specialty;
      } else if (userRow.specialization) {
        defaultData.specialty = userRow.specialization;
      }
      defaultData.consultationFee = String(booking.consultation_fee ?? org.consultation_fee ?? '');
      if (org.country_code) defaultData.countryCode = org.country_code;
      if (org.currency_code) defaultData.currencyCode = org.currency_code;
      if (org.currency_symbol) defaultData.currencySymbol = org.currency_symbol;
      if (org.city) defaultData.city = org.city;
      if (org.address) defaultData.clinicAddress = org.address;
      if (org.timezone) defaultData.timezone = org.timezone;
      if (org.phone) {
        defaultData.doctorPhone = org.phone;
      } else if (userRow.phone_number) {
        defaultData.doctorPhone = userRow.phone_number;
      }
      if (voiceAi.emergency_deflection_phone || org.emergency_deflection_phone) {
        defaultData.emergencyPhone = voiceAi.emergency_deflection_phone || org.emergency_deflection_phone;
      } else {
        defaultData.emergencyPhone = getEmergencyNumberByCountry(defaultData.countryCode);
      }
      defaultData.slotDuration = String(booking.default_slot_duration_minutes ?? org.default_slot_duration_minutes ?? '');
      defaultData.slotBuffer = String(booking.slot_buffer_minutes ?? org.slot_buffer_minutes ?? '');
      defaultData.maxDailyPatients = String(booking.max_daily_patients ?? org.max_daily_patients ?? '');
      defaultData.greetingPrompt = voiceAi.ai_greeting_prompt || org.ai_greeting_prompt || defaultData.greetingPrompt;
      defaultData.voicePersona = normalizeVoicePersona(voiceAi.ai_voice_name || org.ai_voice_name || defaultData.voicePersona);
      defaultData.languageMode = voiceAi.ai_language_mode || org.ai_language_mode || defaultData.languageMode;
      if (booking.weekly_schedule && typeof booking.weekly_schedule === 'object') {
        defaultData.weeklyHours = normalizeWeeklySchedule(booking.weekly_schedule);
      } else if (org.weekly_schedule && typeof org.weekly_schedule === 'object') {
        defaultData.weeklyHours = normalizeWeeklySchedule(org.weekly_schedule);
      }
      return defaultData;
    }
  }

  return defaultData;
}

export function useClinicSettingsQuery() {
  const orgId = useClinicStore((state) => state.orgId);
  const doctorId = useClinicStore((state) => state.doctorId);
  return useQuery({
    queryKey: ['clinic-settings', orgId, doctorId],
    queryFn: async () => {
      const { data, error } = await createClient().from('users').select('*, organizations(*)').eq('id', doctorId).eq('org_id', orgId).single();
      if (error) throw error;
      return mapClinicSettings(data, data.email);
    },
    enabled: Boolean(orgId && doctorId),
  });
}

export interface SaveClinicPayload {
  orgId: string;
  countryName: string;
  data: ClinicSettingsData;
}

export async function saveClinicSettings(payload: SaveClinicPayload): Promise<void> {
  const supabase = createClient();
  const { orgId, countryName, data } = payload;
  const { data: existingOrg, error: existingOrgError } = await supabase.from('organizations').select('booking_settings').eq('id', orgId).maybeSingle();
  if (existingOrgError || !existingOrg) throw existingOrgError || new Error('Organization could not be loaded.');
  if (!data.countryCode || !countryName || !data.currencyCode || !data.timezone) {
    throw new Error('Country, currency, and timezone are required.');
  }
  const slotDuration = Number(data.slotDuration);
  const slotBuffer = Number(data.slotBuffer);
  const maxDailyPatients = Number(data.maxDailyPatients);
  if (!Number.isInteger(slotDuration) || slotDuration <= 0 || !Number.isInteger(slotBuffer) || slotBuffer < 0 || !Number.isInteger(maxDailyPatients) || maxDailyPatients <= 0) {
    throw new Error('Valid slot duration, buffer, and daily capacity are required.');
  }

  const existingVersion = (existingOrg as any)?.voice_ai_settings?.settings_version;

  await httpClient.patch(API_ROUTES.org.byId(orgId), {
    name: data.clinicName,
    lead_doctor_name: data.doctorName,
    clinic_specialty: data.specialty,
    consultation_fee: data.consultationFee ? parseInt(data.consultationFee, 10) : null,
    country: countryName,
    country_code: data.countryCode,
    currency_code: data.currencyCode,
    currency_symbol: data.currencySymbol,
    city: data.city,
    address: data.clinicAddress,
    timezone: data.timezone,
    phone: data.doctorPhone,
    default_slot_duration_minutes: slotDuration,
    slot_buffer_minutes: slotBuffer,
    max_daily_patients: maxDailyPatients,
    weekly_schedule: data.weeklyHours,
    emergency_deflection_phone: data.emergencyPhone,
    ai_greeting_prompt: data.greetingPrompt,
    ai_voice_name: data.voicePersona,
    ai_language_mode: data.languageMode,
    settings_version: existingVersion,
  }, { orgId });

  const { data: { user } } = await supabase.auth.getUser();
  if (user?.email) {
    try {
      await supabase
        .from('users')
        .update({
          full_name: data.doctorName,
          specialization: data.specialty,
          phone_number: data.doctorPhone,
        })
        .eq('email', user.email);
    } catch { }
  }
}

export function useSaveClinicSettingsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveClinicSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clinic-settings'] });
      queryClient.invalidateQueries({ queryKey: ['clinic-organization'] });
      queryClient.invalidateQueries({ queryKey: ['clinic', 'billing-catalog'] });
    },
  });
}
