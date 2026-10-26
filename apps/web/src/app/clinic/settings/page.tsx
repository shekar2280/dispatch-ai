'use client';

import React, { useEffect } from 'react';
import { Save, Check, Loader2, AlertCircle, X, RotateCcw } from 'lucide-react';
import { ClinicSettingsProvider, useClinicSettings } from '../_context/ClinicSettingsContext';
import { useClinicStore } from '../store';
import { DoctorProfileSection } from './_components/DoctorProfileSection';
import { AiVoiceSection } from './_components/AiVoiceSection';
import { OpdScheduleSection } from './_components/OpdScheduleSection';
import { StaffAccessSection } from './_components/StaffAccessSection';
import { BillingCatalogSection } from './_components/BillingCatalogSection';

interface NavItem {
  id: 'doctor-profile' | 'ai-voice' | 'opd-schedule' | 'staff-access' | 'billing-catalog';
  label: string;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'CLINIC',
    items: [
      { id: 'doctor-profile', label: 'Profile' },
      { id: 'opd-schedule', label: 'Appointments & hours' },
      { id: 'staff-access', label: 'Staff access' },
    ],
  },
  {
    title: 'RECEPTION',
    items: [
      { id: 'ai-voice', label: 'Voice & greeting' },
    ],
  },
  { title: 'VISIT RATES', items: [{ id: 'billing-catalog', label: 'Visit rates & items' }] },
];

function ClinicSettingsContent() {
  const activeSection = useClinicStore((s) => s.activeSettingsTab);
  const setActiveSection = useClinicStore((s) => s.setActiveSettingsTab);
  const activeRole = useClinicStore((s) => s.activeRole);
  const visibleSection = activeRole === 'receptionist' ? 'billing-catalog' : activeSection;
  const {
    unsavedCount,
    isSaving,
    isLoading,
    loadError,
    retryLoad,
    isSaved,
    handleSave,
    handleRevert,
    validationError,
    setValidationError,
  } = useClinicSettings();

  useEffect(() => {
    if (activeRole === 'receptionist' && activeSection !== 'billing-catalog') setActiveSection('billing-catalog');
  }, [activeRole, activeSection, setActiveSection]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get('tab');
      if (tabParam === 'voice' || tabParam === 'phone') {
        setActiveSection('ai-voice');
      } else if (tabParam === 'schedule' || tabParam === 'opd') {
        setActiveSection('opd-schedule');
      } else if (tabParam === 'profile') {
        setActiveSection('doctor-profile');
      } else if (tabParam === 'staff' || tabParam === 'personnel' || tabParam === 'desk') {
        setActiveSection('staff-access');
      }
    }
  }, [setActiveSection]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (activeSection === 'opd-schedule') {
        localStorage.setItem('dispatch_onboarding_opd_completed', 'true');
        window.dispatchEvent(new Event('dispatch_onboarding_updated'));
      } else if (activeSection === 'ai-voice') {
        localStorage.setItem('dispatch_onboarding_voice_completed', 'true');
        window.dispatchEvent(new Event('dispatch_onboarding_updated'));
      }
    }
  }, [activeSection]);

  if (isLoading) {
    return (
      <div role="status" className="flex items-center justify-center gap-2 p-10 text-sm text-neutral-500">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        Loading clinic settings…
      </div>
    );
  }

  if (loadError) {
    return (
      <div role="alert" className="m-6 rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900">
        <p className="font-semibold">Unable to load clinic settings</p>
        <p className="mt-1">Check your connection and try again.</p>
        <button type="button" onClick={retryLoad} className="mt-3 rounded-lg border border-rose-200 bg-white px-3 py-2 font-semibold hover:bg-rose-100">
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col font-sans text-neutral-900 min-h-0 bg-[#FAF9F6]">
      <div className="flex-1 flex flex-col md:flex-row min-h-0">
        <aside className="w-full md:w-[220px] md:shrink-0 border-b md:border-b-0 md:border-r border-neutral-200/80 bg-white/70 flex flex-col md:justify-between overflow-hidden md:overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden p-2.5 md:p-3.5">
          <div className="space-y-4">
            <div>
              <h2 className="hidden md:block text-[11px] font-extrabold uppercase tracking-wider text-neutral-500 px-2.5 pt-1">
                Clinic settings
              </h2>
            </div>

            <nav aria-label="Settings sections" className="flex md:block gap-4 md:space-y-3.5 overflow-x-auto md:overflow-visible [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {NAV_GROUPS.filter((group) => activeRole !== 'receptionist' || group.items.some((item) => item.id === 'billing-catalog')).map((group) => (
                <div key={group.title} className="shrink-0 md:space-y-0.5">
                  <p className="hidden md:block text-[10px] font-extrabold uppercase tracking-wider text-neutral-500 px-2.5 mb-1">
                    {group.title}
                  </p>
                  <div className="flex md:block gap-1 md:space-y-0.5">
                    {group.items.filter((item) => activeRole !== 'receptionist' || item.id === 'billing-catalog').map((item) => {
                      const isActive = visibleSection === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setActiveSection(item.id)}
                          aria-current={isActive ? 'page' : undefined}
                          className={`w-full whitespace-nowrap text-left px-3 md:px-2.5 py-2 md:py-1.5 rounded-lg text-xs transition-all duration-150 cursor-pointer ${
                            isActive
                              ? 'bg-neutral-200/90 text-neutral-950 font-bold'
                              : 'text-neutral-700 hover:text-neutral-950 hover:bg-neutral-100 font-semibold'
                          }`}
                        >
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>
          </div>


        </aside>

        <main className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto min-h-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden px-4 sm:px-8 py-5 sm:py-7 pb-8">
            <div className="max-w-[920px] space-y-5">
            <div className="pb-1">
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-neutral-950">
                {visibleSection === 'doctor-profile' && 'Clinic profile'}
                {visibleSection === 'opd-schedule' && 'Appointments & hours'}
                {visibleSection === 'staff-access' && 'Staff access'}
                {visibleSection === 'ai-voice' && 'Voice & greeting'}
                {visibleSection === 'billing-catalog' && 'Visit rates & items'}
              </h1>
              <p className="text-sm text-neutral-500 mt-1 font-normal">
                {visibleSection === 'doctor-profile' && 'Update clinic details, doctor contact information, and emergency routing.'}
                {visibleSection === 'opd-schedule' && 'Set appointment lengths, daily capacity, and consultation hours.'}
                {visibleSection === 'staff-access' && 'Manage secure sign-in for your reception team.'}
                {visibleSection === 'ai-voice' && 'Choose the receptionist voice and the greeting callers hear.'}
                {visibleSection === 'billing-catalog' && 'Set visit charges and reusable medicine or service prices for check-in and checkout.'}
              </p>
            </div>

            {validationError && (
              <div className="flex items-center justify-between gap-3 p-3 bg-rose-50 border border-rose-200/90 rounded-xl text-rose-800 text-xs shadow-2xs animate-in fade-in slide-in-from-top-1">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  <span className="font-medium">{validationError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setValidationError(null)}
                  className="p-1 hover:bg-rose-100 rounded-lg text-rose-600 transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {visibleSection === 'doctor-profile' && <DoctorProfileSection />}
            {visibleSection === 'opd-schedule' && <OpdScheduleSection />}
            {visibleSection === 'staff-access' && <StaffAccessSection />}
            {visibleSection === 'ai-voice' && <AiVoiceSection />}
            {visibleSection === 'billing-catalog' && <BillingCatalogSection />}
            </div>
          </div>

          {activeRole !== 'receptionist' && (unsavedCount > 0 || isSaving || isSaved) && (
            <div className="shrink-0 border-t border-neutral-200/80 bg-[#FAF9F6]/95 backdrop-blur px-4 sm:px-8 py-3 sm:py-4">
              <div
                role="status"
                aria-live="polite"
                className={`mx-auto max-w-[920px] flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border px-4 py-3 shadow-sm ${
                  isSaving
                    ? 'bg-neutral-900 text-white border-neutral-800'
                    : unsavedCount > 0
                    ? 'bg-white text-neutral-900 border-neutral-200'
                    : 'bg-emerald-50 text-emerald-950 border-emerald-200'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                    isSaving
                      ? 'bg-white/10 text-white'
                      : unsavedCount > 0
                      ? 'bg-amber-50 text-amber-700'
                      : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    {isSaving ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : unsavedCount > 0 ? (
                      <AlertCircle className="w-4 h-4" />
                    ) : (
                      <Check className="w-4 h-4 stroke-[2.5]" />
                    )}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">
                      {isSaving ? 'Saving your changes' : unsavedCount > 0 ? 'You have unsaved changes' : 'Changes saved'}
                    </span>
                    <span className={`block text-xs mt-0.5 ${isSaving ? 'text-neutral-300' : unsavedCount > 0 ? 'text-neutral-500' : 'text-emerald-800'}`}>
                      {isSaving
                        ? 'Updating your clinic settings…'
                        : unsavedCount > 0
                        ? `${unsavedCount} ${unsavedCount === 1 ? 'update' : 'updates'} will be saved across your clinic settings.`
                        : 'Your clinic settings are up to date.'}
                    </span>
                  </span>
                </div>

                {unsavedCount > 0 && (
                  <div className="flex items-center gap-2 sm:shrink-0">
                    <button
                      type="button"
                      onClick={handleRevert}
                      disabled={isSaving}
                      className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-neutral-700 bg-white hover:bg-neutral-100 border border-neutral-200 transition-colors disabled:opacity-50"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Discard</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSave()}
                      disabled={isSaving}
                      className="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-neutral-950 hover:bg-neutral-800 shadow-sm transition-colors disabled:opacity-60"
                    >
                      {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      <span>{isSaving ? 'Saving…' : 'Save changes'}</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

    </div>
  );
}

export default function ClinicSettingsPage() {
  return (
    <ClinicSettingsProvider>
      <ClinicSettingsContent />
    </ClinicSettingsProvider>
  );
}
