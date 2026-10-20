'use client';

import React, { useState, useEffect } from 'react';
import {
  Building2, User, Mail, Phone, Stethoscope, MapPin,
  ShieldAlert, AlertTriangle, Trash2, X, Loader2,
  Building, Globe, Clock,
} from 'lucide-react';
import { useClinicSettings } from '../../_context/ClinicSettingsContext';
import { ALL_COUNTRIES, getTimezoneGroupsForCountry } from '@/lib/country-metadata';

export function DoctorProfileSection() {
  const {
    clinicName, setClinicName,
    doctorName, setDoctorName,
    specialty, setSpecialty,
    countryCode,
    countryProfile,
    handleCountryChange,
    emergencyPhone, setEmergencyPhone,
    doctorEmail, setDoctorEmail,
    doctorPhone, setDoctorPhone,
    city, setCity,
    clinicAddress, setClinicAddress,
    timezone, setTimezone,
    deleteModalOpen, setDeleteModalOpen,
    isDeletingAccount, handleDeleteAccount,
  } = useClinicSettings();

  const [confirmClinicName, setConfirmClinicName] = useState('');
  const [localTimeDisplay, setLocalTimeDisplay] = useState('');
  const timezoneGroups = React.useMemo(
    () => getTimezoneGroupsForCountry(countryCode, countryProfile.name),
    [countryCode, countryProfile.name]
  );

  useEffect(() => {
    const updateTime = () => {
      if (!timezone) {
        setLocalTimeDisplay('Select timezone');
        return;
      }
      try {
        const now = new Date();
        const formatted = new Intl.DateTimeFormat('en-US', {
          timeZone: timezone || undefined,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
          timeZoneName: 'shortOffset',
        }).format(now);
        setLocalTimeDisplay(formatted);
      } catch {
        setLocalTimeDisplay(timezone || 'Select timezone');
      }
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, [timezone]);

  const isDeleteConfirmed = confirmClinicName.trim() === clinicName.trim();

  return (
    <div className="space-y-6 animate-fade-in">
      <section className="space-y-2">
        <h3 className="text-sm font-bold text-neutral-950">Clinic and doctor details</h3>

        <div className="bg-white border border-neutral-200/80 rounded-xl p-4 shadow-2xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-neutral-400" />
                <span>Clinic Name</span>
              </label>
              <input
                type="text"
                value={clinicName}
                onChange={(e) => setClinicName(e.target.value)}
                placeholder="e.g. City Care & Wellness Clinic"
                className="w-full h-9 px-3 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-neutral-400" />
                <span>Doctor Name</span>
              </label>
              <input
                type="text"
                value={doctorName}
                onChange={(e) => setDoctorName(e.target.value)}
                placeholder="e.g. Dr. Priya Patel"
                className="w-full h-9 px-3 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-neutral-400" />
                <span>Email</span>
              </label>
              <input
                type="email"
                value={doctorEmail}
                onChange={(e) => setDoctorEmail(e.target.value)}
                placeholder="e.g. doctor@clinic.com"
                className="w-full h-9 px-3 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                <Phone className="w-3.5 h-3.5 text-neutral-400" />
                <span>Doctor Phone</span>
              </label>
              <div className="flex rounded-lg border border-neutral-200 bg-white shadow-2xs focus-within:border-neutral-950 focus-within:ring-1 focus-within:ring-neutral-950/10 transition-all overflow-hidden h-9">
                <div className="relative shrink-0 border-r border-neutral-200 bg-neutral-50/80 hover:bg-neutral-100/80 transition-colors flex items-center">
                  <select
                    value={countryCode}
                    onChange={(e) => handleCountryChange(e.target.value)}
                    className="h-full pl-2.5 pr-6 text-xs font-semibold text-neutral-800 bg-transparent outline-none cursor-pointer appearance-none"
                    title={`Region: ${countryProfile.name} (${countryProfile.phoneCode})`}
                  >
                    <option value="">Select country</option>
                    {ALL_COUNTRIES.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.flag} {c.code} ({c.phoneCode})
                      </option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-1.5 flex items-center text-neutral-400 text-[10px]">
                    ▾
                  </div>
                </div>
                <input
                  type="tel"
                  value={doctorPhone}
                  onChange={(e) => setDoctorPhone(e.target.value)}
                  placeholder="98765 43210"
                  className="w-full px-3 text-xs bg-transparent font-medium text-neutral-900 outline-none font-mono"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                <Stethoscope className="w-3.5 h-3.5 text-neutral-400" />
                <span>Specialty</span>
              </label>
              <input
                type="text"
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                placeholder="Pediatrics & General Practice"
                className="w-full h-9 px-3 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                <Building className="w-3.5 h-3.5 text-neutral-400" />
                <span>City</span>
              </label>
              <input
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="e.g. Mumbai, New York, London"
                className="w-full h-9 px-3 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-neutral-400" />
                  <span>Clinic Street Address</span>
                </span>
              </label>
              <textarea
                value={clinicAddress}
                onChange={(e) => setClinicAddress(e.target.value)}
                placeholder="Suite 101, Medical Enclave, Main Road, Landmark"
                rows={2}
                className="w-full h-[76px] px-3 py-2 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs resize-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-neutral-700 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-neutral-400" />
                  <span>Practice Timezone</span>
                </span>
                <span className="text-[10px] text-neutral-400 font-mono">{timezone}</span>
              </label>
              <div className="space-y-1.5">
                <div className="relative">
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full h-9 pl-3 pr-8 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-neutral-950 focus:ring-1 focus:ring-neutral-950/10 transition-all shadow-2xs cursor-pointer appearance-none"
                  >
                    {!timezoneGroups.some((g) => g.options.some((o) => o.value === timezone)) && (
                      <option value={timezone}>{timezone || 'Select timezone'}</option>
                    )}
                    {timezoneGroups.map((group) => (
                      <optgroup key={group.region} label={group.region}>
                        {group.options.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-neutral-400 text-xs">
                    ▾
                  </div>
                </div>

                <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-neutral-50/80 border border-neutral-200/60 text-[11px] text-neutral-600">
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3 h-3 text-neutral-400" />
                    <span>Clinic Local Time</span>
                  </span>
                  <span className="font-mono font-medium text-neutral-800">{localTimeDisplay}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-neutral-950">Emergency contact</h3>
        </div>

        <div className="bg-white border border-rose-200/80 rounded-xl p-4 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3 max-w-xl">
            <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center shrink-0 mt-0.5">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-xs font-semibold text-neutral-950">Emergency Hotline</p>
              </div>
              <p className="text-xs text-neutral-500 leading-relaxed">
                When a caller reports a medical emergency, the receptionist directs them to this number. Confirm it matches your local emergency process.
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 shrink-0">
            <div className="relative w-full sm:w-36">
              <Phone className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-rose-500" />
              <input
                type="text"
                value={emergencyPhone}
                onChange={(e) => setEmergencyPhone(e.target.value)}
                placeholder="Local ambulance or emergency service number"
                className="w-full h-9 pl-8 pr-3 text-xs bg-white border border-rose-300 rounded-lg font-mono font-bold text-rose-950 outline-none focus:border-rose-600 shadow-2xs"
              />
            </div>

          </div>
        </div>
      </section>

      <section className="space-y-2 pt-2">
        <h3 className="text-sm font-bold text-rose-950">Account deletion</h3>

        <div className="bg-rose-50/20 border border-rose-200 rounded-xl p-4 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3 max-w-xl">
            <div className="w-8 h-8 rounded-lg bg-rose-100/70 border border-rose-200 text-rose-700 flex items-center justify-center shrink-0 mt-0.5">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="space-y-0.5">
              <p className="text-xs font-semibold text-rose-950">Delete practice account</p>
              <p className="text-xs text-rose-700/80 leading-relaxed">
                Permanently delete this clinic account and its records. This action cannot be undone.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setConfirmClinicName('');
              setDeleteModalOpen(true);
            }}
            className="flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-tight text-rose-700 bg-white border border-rose-300 hover:bg-rose-50 hover:border-rose-400 transition-all duration-150 cursor-pointer shadow-2xs active:scale-[0.98] shrink-0 self-start sm:self-auto"
          >
            <Trash2 className="w-3.5 h-3.5 text-rose-600" />
            <span>Delete practice account</span>
          </button>
        </div>
      </section>

      {deleteModalOpen && (
        <div className="fixed inset-0 z-50 bg-neutral-950/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-neutral-200 rounded-2xl p-5 max-w-md w-full shadow-2xl space-y-4 animate-scale-in">
            <div className="flex items-start justify-between gap-3">
              <div className="w-9 h-9 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <button
                type="button"
                onClick={() => setDeleteModalOpen(false)}
                className="w-7 h-7 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 flex items-center justify-center cursor-pointer transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-1.5">
              <h4 className="text-base font-bold text-neutral-950">Delete Practice Workspace</h4>
              <p className="text-xs text-neutral-500 leading-relaxed">
                This will permanently delete <span className="font-semibold text-neutral-900">{clinicName}</span> and its schedules, patient queue data, and receptionist settings.
              </p>
            </div>

            <div className="space-y-1.5 pt-1">
              <label className="text-xs font-medium text-neutral-700 block">
                Enter <span className="font-bold text-neutral-950 select-all">{clinicName}</span> to confirm:
              </label>
              <input
                type="text"
                value={confirmClinicName}
                onChange={(e) => setConfirmClinicName(e.target.value)}
                placeholder={clinicName}
                className="w-full h-9 px-3 text-xs bg-white border border-neutral-200 rounded-lg font-medium text-neutral-900 outline-none focus:border-rose-600 focus:ring-1 focus:ring-rose-600/20 transition-all shadow-2xs"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-neutral-100">
              <button
                type="button"
                onClick={() => setDeleteModalOpen(false)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-neutral-600 hover:bg-neutral-100 transition-colors cursor-pointer"
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={!isDeleteConfirmed || isDeletingAccount}
                onClick={handleDeleteAccount}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${isDeleteConfirmed && !isDeletingAccount
                    ? 'bg-rose-600 text-white hover:bg-rose-700 shadow-sm cursor-pointer active:scale-[0.98]'
                    : 'bg-rose-200 text-rose-400 cursor-not-allowed'
                  }`}
              >
                {isDeletingAccount ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Permanently Delete</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
