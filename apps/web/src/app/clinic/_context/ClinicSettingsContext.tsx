'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase/client';
import {
  DEFAULT_WEEKLY_HOURS, DaySchedule, VOICE_PERSONAS,
  DEFAULT_CLINIC_PROFILE, VoicePersona,
} from '../constants';
import { API_ROUTES } from '@/lib/constants';
import { httpClient } from '@/lib/api/httpClient';
import {
  getCountryProfile,
  ALL_COUNTRIES,
  ALL_CURRENCIES,
  getCurrencyForCode,
  CountryOption,
} from '@/lib/country-metadata';
import { useVoiceAudioPreview } from '../_hooks/useVoiceAudioPreview';
import {
  useClinicSettingsQuery,
  useSaveClinicSettingsMutation,
} from '../_hooks/useClinicQuery';
import { useClinicSchedule } from '../_hooks/useClinicSchedule';
import { getEmergencyNumberByCountry } from '@/lib/emergencyNumbers';

const ORDERED_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const;

interface ClinicSettingsContextType {
  orgId: string;
  clinicName: string;
  setClinicName: (v: string) => void;
  doctorName: string;
  doctorNameInitial?: string;
  setDoctorName: (v: string) => void;
  specialty: string;
  setSpecialty: (v: string) => void;
  consultationFee: string;
  setConsultationFee: (v: string) => void;
  countryCode: string;
  setCountryCode: (v: string) => void;
  currencyCode: string;
  setCurrencyCode: (v: string) => void;
  currencySymbol: string;
  setCurrencySymbol: (v: string) => void;
  countryProfile: CountryOption;
  handleCountryChange: (code: string) => void;
  handleCurrencyChange: (currency: string) => void;
  emergencyPhone: string;
  setEmergencyPhone: (v: string) => void;
  doctorEmail: string;
  setDoctorEmail: (v: string) => void;
  doctorPhone: string;
  setDoctorPhone: (v: string) => void;
  registrationNumber: string;
  setRegistrationNumber: (v: string) => void;
  city: string;
  setCity: (v: string) => void;
  clinicAddress: string;
  setClinicAddress: (v: string) => void;
  timezone: string;
  setTimezone: (v: string) => void;
  deleteModalOpen: boolean;
  setDeleteModalOpen: (v: boolean) => void;
  isDeletingAccount: boolean;
  handleDeleteAccount: () => Promise<void>;
  slotDuration: string;
  setSlotDuration: (v: string) => void;
  slotBuffer: string;
  setSlotBuffer: (v: string) => void;
  maxDailyPatients: string;
  setMaxDailyPatients: (v: string) => void;
  weeklyHours: Record<string, DaySchedule>;
  greetingPrompt: string;
  setGreetingPrompt: (v: string) => void;
  initialGreetingPrompt: string;
  voicePersona: string;
  setVoicePersona: (v: string) => void;
  initialVoicePersona: string;
  isLoadingAudio: boolean;
  audioPreviewError: string | null;
  languageMode: string;
  setLanguageMode: (v: string) => void;
  unsavedCount: number;
  isSaving: boolean;
  isLoading: boolean;
  loadError: boolean;
  retryLoad: () => void;
  isSaved: boolean;
  isPlayingAudio: boolean;
  playingSampleId: string | null;
  loadingSampleId: string | null;
  validationError: string | null;
  setValidationError: (v: string | null) => void;
  handleSave: (e?: React.FormEvent) => Promise<void>;
  handleSelectVoice: (v: VoicePersona) => void;
  playPersonaSample: (e: React.MouseEvent, persona: VoicePersona) => void;
  playGreetingPreview: (customText?: string, customVoiceId?: string) => Promise<void>;
  stopAudioPreview: () => void;
  handleDayToggle: (day: string) => void;
  handleTimeChange: (day: string, field: keyof DaySchedule, value: string) => void;
  copyMondayToWeekdays: () => void;
  handleRevert: () => void;
}

const ClinicSettingsContext = createContext<ClinicSettingsContextType | null>(null);

export function ClinicSettingsProvider({ children }: { children: React.ReactNode }) {
  const { data: serverData, isPending: isLoading, isError: loadError, refetch } = useClinicSettingsQuery();
  const saveMutation = useSaveClinicSettingsMutation();

  const [orgId, setOrgId] = useState(serverData?.orgId || '');
  const [clinicName, setClinicName] = useState(DEFAULT_CLINIC_PROFILE.clinicName);
  const [initialClinicName, setInitialClinicName] = useState(DEFAULT_CLINIC_PROFILE.clinicName);
  const [doctorName, setDoctorName] = useState(DEFAULT_CLINIC_PROFILE.doctorName);
  const [initialDoctorName, setInitialDoctorName] = useState(DEFAULT_CLINIC_PROFILE.doctorName);
  const [specialty, setSpecialty] = useState(DEFAULT_CLINIC_PROFILE.specialty);
  const [initialSpecialty, setInitialSpecialty] = useState(DEFAULT_CLINIC_PROFILE.specialty);
  const [consultationFee, setConsultationFee] = useState(DEFAULT_CLINIC_PROFILE.consultationFee);
  const [initialConsultationFee, setInitialConsultationFee] = useState(DEFAULT_CLINIC_PROFILE.consultationFee);
  const [countryCode, setCountryCode] = useState('');
  const [initialCountryCode, setInitialCountryCode] = useState('');
  const [currencyCode, setCurrencyCode] = useState('');
  const [initialCurrencyCode, setInitialCurrencyCode] = useState('');
  const [currencySymbol, setCurrencySymbol] = useState('');
  const [initialCurrencySymbol, setInitialCurrencySymbol] = useState('');
  const [emergencyPhone, setEmergencyPhone] = useState(DEFAULT_CLINIC_PROFILE.emergencyPhone);
  const [initialEmergencyPhone, setInitialEmergencyPhone] = useState(DEFAULT_CLINIC_PROFILE.emergencyPhone);
  const [doctorEmail, setDoctorEmail] = useState(DEFAULT_CLINIC_PROFILE.doctorEmail);
  const [initialDoctorEmail, setInitialDoctorEmail] = useState(DEFAULT_CLINIC_PROFILE.doctorEmail);
  const [doctorPhone, setDoctorPhone] = useState(DEFAULT_CLINIC_PROFILE.doctorPhone);
  const [initialDoctorPhone, setInitialDoctorPhone] = useState(DEFAULT_CLINIC_PROFILE.doctorPhone);
  const [registrationNumber, setRegistrationNumber] = useState(DEFAULT_CLINIC_PROFILE.registrationNumber);
  const [city, setCity] = useState(DEFAULT_CLINIC_PROFILE.city || '');
  const [initialCity, setInitialCity] = useState(DEFAULT_CLINIC_PROFILE.city || '');
  const [clinicAddress, setClinicAddress] = useState(DEFAULT_CLINIC_PROFILE.clinicAddress);
  const [initialClinicAddress, setInitialClinicAddress] = useState(DEFAULT_CLINIC_PROFILE.clinicAddress);
  const [timezone, setTimezone] = useState('');
  const [initialTimezone, setInitialTimezone] = useState('');
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [slotDuration, setSlotDuration] = useState('15');
  const [initialSlotDuration, setInitialSlotDuration] = useState('15');
  const [slotBuffer, setSlotBuffer] = useState('5');
  const [initialSlotBuffer, setInitialSlotBuffer] = useState('5');
  const [maxDailyPatients, setMaxDailyPatients] = useState('30');
  const [initialMaxDailyPatients, setInitialMaxDailyPatients] = useState('30');
  const [unsavedCount, setSavedCount] = useState(0);
  const [greetingPrompt, setGreetingPrompt] = useState(DEFAULT_CLINIC_PROFILE.defaultGreetingPrompt);
  const [initialGreetingPrompt, setInitialGreetingPrompt] = useState(DEFAULT_CLINIC_PROFILE.defaultGreetingPrompt);
  const [voicePersona, setVoicePersona] = useState('priya');
  const [initialVoicePersona, setInitialVoicePersona] = useState('priya');
  const [languageMode, setLanguageMode] = useState('en_hi_bilingual');
  const [initialLanguageMode, setInitialLanguageMode] = useState('en_hi_bilingual');

  const [isSaved, setIsSaved] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const {
    weeklyHours,
    initialWeeklyHours,
    handleDayToggle,
    handleTimeChange,
    copyMondayToWeekdays,
    syncSchedule,
    commitSchedule,
  } = useClinicSchedule();

  const {
    isPlayingAudio,
    isLoadingAudio,
    audioPreviewError,
    playingSampleId,
    loadingSampleId,
    playGreetingPreview,
    playPersonaSample,
    stopAudioPreview,
  } = useVoiceAudioPreview({
    clinicName,
    greetingPrompt,
    voicePersona,
  });

  useEffect(() => {
    if (!serverData) return;
    setOrgId(serverData.orgId);
    setClinicName(serverData.clinicName);
    setInitialClinicName(serverData.clinicName);
    setDoctorName(serverData.doctorName);
    setInitialDoctorName(serverData.doctorName);
    setDoctorEmail(serverData.doctorEmail);
    setInitialDoctorEmail(serverData.doctorEmail);
    setDoctorPhone(serverData.doctorPhone);
    setInitialDoctorPhone(serverData.doctorPhone);
    setSpecialty(serverData.specialty);
    setInitialSpecialty(serverData.specialty);
    setConsultationFee(serverData.consultationFee);
    setInitialConsultationFee(serverData.consultationFee);
    setCountryCode(serverData.countryCode);
    setInitialCountryCode(serverData.countryCode);
    setCurrencyCode(serverData.currencyCode);
    setInitialCurrencyCode(serverData.currencyCode);
    setCurrencySymbol(serverData.currencySymbol);
    setInitialCurrencySymbol(serverData.currencySymbol);
    setCity(serverData.city || '');
    setInitialCity(serverData.city || '');
    setClinicAddress(serverData.clinicAddress || '');
    setInitialClinicAddress(serverData.clinicAddress || '');
    setTimezone(serverData.timezone);
    setInitialTimezone(serverData.timezone);
    setEmergencyPhone(serverData.emergencyPhone);
    setInitialEmergencyPhone(serverData.emergencyPhone);
    setSlotDuration(serverData.slotDuration);
    setInitialSlotDuration(serverData.slotDuration);
    setSlotBuffer(serverData.slotBuffer);
    setInitialSlotBuffer(serverData.slotBuffer);
    setMaxDailyPatients(serverData.maxDailyPatients);
    setInitialMaxDailyPatients(serverData.maxDailyPatients);
    setGreetingPrompt(serverData.greetingPrompt);
    setInitialGreetingPrompt(serverData.greetingPrompt);
    setVoicePersona(serverData.voicePersona);
    setInitialVoicePersona(serverData.voicePersona);
    setLanguageMode(serverData.languageMode);
    setInitialLanguageMode(serverData.languageMode);
    syncSchedule(serverData.weeklyHours);
  }, [serverData, syncSchedule]);

  useEffect(() => {
    let count = 0;
    if (clinicName.trim() !== initialClinicName.trim()) count++;
    if (doctorName.trim() !== initialDoctorName.trim()) count++;
    if (doctorEmail.trim() !== initialDoctorEmail.trim()) count++;
    if (doctorPhone.trim() !== initialDoctorPhone.trim()) count++;
    if (specialty.trim() !== initialSpecialty.trim()) count++;
    if (consultationFee.trim() !== initialConsultationFee.trim()) count++;
    if (city.trim() !== initialCity.trim()) count++;
    if (clinicAddress.trim() !== initialClinicAddress.trim()) count++;
    if (timezone !== initialTimezone) count++;
    if (emergencyPhone.trim() !== initialEmergencyPhone.trim()) count++;
    if (countryCode !== initialCountryCode) count++;
    if (currencyCode !== initialCurrencyCode) count++;
    if (currencySymbol !== initialCurrencySymbol) count++;
    if (slotDuration !== initialSlotDuration) count++;
    if (slotBuffer !== initialSlotBuffer) count++;
    if (maxDailyPatients !== initialMaxDailyPatients) count++;
    if (greetingPrompt !== initialGreetingPrompt) count++;
    if (voicePersona !== initialVoicePersona) count++;
    if (languageMode !== initialLanguageMode) count++;
    ORDERED_DAYS.forEach((day) => {
      const c = weeklyHours[day];
      const i = initialWeeklyHours[day];
      if (
        !i || !c ||
        c.isOpen !== i.isOpen ||
        c.morningStart !== i.morningStart ||
        c.morningEnd !== i.morningEnd ||
        c.eveningStart !== i.eveningStart ||
        c.eveningEnd !== i.eveningEnd
      ) {
        count++;
      }
    });
    setSavedCount(count);
  }, [
    clinicName, initialClinicName,
    doctorName, initialDoctorName,
    doctorEmail, initialDoctorEmail,
    doctorPhone, initialDoctorPhone,
    specialty, initialSpecialty,
    consultationFee, initialConsultationFee,
    city, initialCity,
    clinicAddress, initialClinicAddress,
    timezone, initialTimezone,
    emergencyPhone, initialEmergencyPhone,
    countryCode, initialCountryCode,
    currencyCode, initialCurrencyCode,
    currencySymbol, initialCurrencySymbol,
    slotDuration, initialSlotDuration,
    slotBuffer, initialSlotBuffer,
    maxDailyPatients, initialMaxDailyPatients,
    weeklyHours, initialWeeklyHours,
    greetingPrompt, initialGreetingPrompt,
    voicePersona, initialVoicePersona,
    languageMode, initialLanguageMode,
  ]);

  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => {
      if (unsavedCount > 0) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [unsavedCount]);

  const countryProfile = getCountryProfile(countryCode);

  const handleCountryChange = (code: string) => {
    setCountryCode(code);
    setCurrencyCode('');
    setCurrencySymbol('');
    setEmergencyPhone(getEmergencyNumberByCountry(code));
    setTimezone('');
  };

  const handleCurrencyChange = (newCurrencyCode: string) => {
    setCurrencyCode(newCurrencyCode);
    const cur = getCurrencyForCode(newCurrencyCode);
    setCurrencySymbol(cur.symbol);
  };

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (saveMutation.isPending) return;

    const cleanClinicName = clinicName.trim();
    if (!cleanClinicName) {
      setValidationError('Clinic Name cannot be empty.');
      return;
    }

    const cleanDoctorName = doctorName.trim();
    if (!cleanDoctorName) {
      setValidationError('Attending Doctor Name cannot be empty.');
      return;
    }

    if (!ALL_COUNTRIES.some((country) => country.code === countryCode) || !ALL_CURRENCIES.some((currency) => currency.code === currencyCode) || !timezone || !emergencyPhone.trim()) {
      setValidationError('Country, currency, timezone, and emergency contact are required.');
      return;
    }
    try {
      new Intl.DateTimeFormat('en-US', { timeZone: timezone });
    } catch {
      setValidationError('Select a valid clinic timezone.');
      return;
    }

    const feeNum = Number(consultationFee);
    if (isNaN(feeNum) || feeNum < 0) {
      setValidationError('Consultation Fee must be a valid non-negative amount.');
      return;
    }

    const durationNum = Number(slotDuration);
    if (isNaN(durationNum) || durationNum <= 0) {
      setValidationError('Slot duration must be greater than 0 minutes.');
      return;
    }

    const maxDailyNum = Number(maxDailyPatients);
    if (isNaN(maxDailyNum) || maxDailyNum <= 0) {
      setValidationError('Maximum daily capacity must be greater than 0.');
      return;
    }

    const cleanEmail = doctorEmail.trim();
    if (cleanEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setValidationError('Please enter a valid Doctor Email address.');
      return;
    }

    setValidationError(null);

    try {
      await saveMutation.mutateAsync({
        orgId,
        countryName: countryProfile.name,
        data: {
          orgId,
          clinicName,
          doctorName,
          doctorEmail,
          doctorPhone,
          specialty,
          consultationFee,
          countryCode,
          currencyCode,
          currencySymbol,
          city,
          clinicAddress,
          timezone,
          emergencyPhone,
          slotDuration,
          slotBuffer,
          maxDailyPatients,
          weeklyHours,
          greetingPrompt,
          voicePersona,
          languageMode,
        },
      });

      setInitialClinicName(clinicName);
      setInitialDoctorName(doctorName);
      setInitialDoctorEmail(doctorEmail);
      setInitialDoctorPhone(doctorPhone);
      setInitialSpecialty(specialty);
      setInitialConsultationFee(consultationFee);
      setInitialCity(city);
      setInitialClinicAddress(clinicAddress);
      setInitialTimezone(timezone);
      setInitialEmergencyPhone(emergencyPhone);
      setInitialCountryCode(countryCode);
      setInitialCurrencyCode(currencyCode);
      setInitialCurrencySymbol(currencySymbol);
      setInitialSlotDuration(slotDuration);
      setInitialSlotBuffer(slotBuffer);
      setInitialMaxDailyPatients(maxDailyPatients);
      commitSchedule();
      setInitialGreetingPrompt(greetingPrompt);
      setInitialVoicePersona(voicePersona);
      setInitialLanguageMode(languageMode);
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2500);
    } catch (error) {
      setValidationError(
        error instanceof Error ? error.message : 'Unable to save clinic settings. Please try again.'
      );
    }
  };

  const handleDeleteAccount = async () => {
    setIsDeletingAccount(true);
    try {
      const supabase = createClient();
      await httpClient.delete(API_ROUTES.org.byId(orgId));
      await supabase.auth.signOut();
      if (typeof window !== 'undefined') {
        localStorage.clear();
        sessionStorage.clear();
        window.location.href = '/login';
      }
    } catch {
    } finally {
      setIsDeletingAccount(false);
      setDeleteModalOpen(false);
    }
  };

  const handleSelectVoice = (v: VoicePersona) => {
    setVoicePersona(v.id);
  };

  const handleRevert = () => {
    setClinicName(initialClinicName);
    setDoctorName(initialDoctorName);
    setDoctorEmail(initialDoctorEmail);
    setDoctorPhone(initialDoctorPhone);
    setSpecialty(initialSpecialty);
    setConsultationFee(initialConsultationFee);
    setCountryCode(initialCountryCode);
    setCurrencyCode(initialCurrencyCode);
    setCurrencySymbol(initialCurrencySymbol);
    setCity(initialCity);
    setClinicAddress(initialClinicAddress);
    setTimezone(initialTimezone);
    setEmergencyPhone(initialEmergencyPhone);
    setSlotDuration(initialSlotDuration);
    setSlotBuffer(initialSlotBuffer);
    setMaxDailyPatients(initialMaxDailyPatients);
    setGreetingPrompt(initialGreetingPrompt);
    setVoicePersona(initialVoicePersona);
    setLanguageMode(initialLanguageMode);
    syncSchedule(initialWeeklyHours);
    setValidationError(null);
  };

  return (
    <ClinicSettingsContext.Provider
      value={{
        orgId,
        clinicName,
        setClinicName,
        doctorName,
        setDoctorName,
        specialty,
        setSpecialty,
        consultationFee,
        setConsultationFee,
        countryCode,
        setCountryCode,
        currencyCode,
        setCurrencyCode,
        currencySymbol,
        setCurrencySymbol,
        countryProfile,
        handleCountryChange,
        handleCurrencyChange,
        emergencyPhone,
        setEmergencyPhone,
        doctorEmail,
        setDoctorEmail,
        doctorPhone,
        setDoctorPhone,
        registrationNumber,
        setRegistrationNumber,
        city,
        setCity,
        clinicAddress,
        setClinicAddress,
        timezone,
        setTimezone,
        deleteModalOpen,
        setDeleteModalOpen,
        isDeletingAccount,
        handleDeleteAccount,
        slotDuration,
        setSlotDuration,
        slotBuffer,
        setSlotBuffer,
        maxDailyPatients,
        setMaxDailyPatients,
        weeklyHours,
        greetingPrompt,
        setGreetingPrompt,
        initialGreetingPrompt,
        voicePersona,
        setVoicePersona,
        initialVoicePersona,
        languageMode,
        setLanguageMode,
        unsavedCount,
        isSaving: saveMutation.isPending,
        isLoading,
        loadError,
        retryLoad: () => { void refetch(); },
        isSaved,
        isLoadingAudio,
        audioPreviewError,
        isPlayingAudio,
        playingSampleId,
    loadingSampleId,
        validationError,
        setValidationError,
        handleSave,
        handleSelectVoice,
        playPersonaSample,
        playGreetingPreview,
        stopAudioPreview,
        handleDayToggle,
        handleTimeChange,
        copyMondayToWeekdays,
        handleRevert,
      }}
    >
      {children}
    </ClinicSettingsContext.Provider>
  );
}

export function useClinicSettings() {
  const context = useContext(ClinicSettingsContext);
  if (!context) {
    throw new Error('useClinicSettings must be used within a ClinicSettingsProvider');
  }
  return context;
}
