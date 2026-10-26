'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  Menu,
  X,
  PhoneCall,
  Plus,
  LogOut,
  User,
  Settings,
  ChevronDown,
  CalendarDays,
  ChevronRight,
} from 'lucide-react';
import { APP_CONFIG } from '@/lib/constants';
import Image from 'next/image';

interface ClinicHeaderProps {
  clinicName: string;
  specialty: string;
  doctorName: string;
  initials: string;
  pageTitle?: string;
  activeRole?: 'doctor' | 'receptionist';
  mobileMenuOpen: boolean;
  onToggleMobile: () => void;
  onOpenVoiceSimulator: () => void;
  onOpenBooking: () => void;
  onSignOut: () => void;
}

export function ClinicHeader({
  clinicName,
  specialty,
  doctorName,
  initials,
  pageTitle,
  activeRole = 'doctor',
  mobileMenuOpen,
  onToggleMobile,
  onOpenVoiceSimulator,
  onOpenBooking,
  onSignOut,
}: ClinicHeaderProps) {
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  const today = new Date().toLocaleDateString('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });

  return (
    <header className="h-[56px] bg-white border-b border-[rgba(13,38,34,0.12)] flex items-center px-3 sm:px-5 justify-between gap-3 shrink-0 relative z-40">
      <div className="flex items-center gap-2 sm:gap-3 min-w-0 shrink">
        <button
          onClick={onToggleMobile}
          className="p-1.5 -ml-1 rounded-md text-[rgba(13,38,34,0.6)] hover:text-[#0D2622] hover:bg-[#F1F4EE] lg:hidden transition-colors"
          aria-label="Toggle navigation"
        >
          {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
        </button>

        <div className="flex items-center gap-1.5 min-w-0 text-[13px]">
          <h1 className="font-medium text-[#0D2622] tracking-tight truncate max-w-[130px] sm:max-w-[220px]">
            {clinicName}
          </h1>
          {pageTitle && (
            <>
              <ChevronRight className="w-3.5 h-3.5 text-[rgba(13,38,34,0.3)] shrink-0 hidden sm:block" />
              <span className="text-[#0D2622]/75 font-normal truncate hidden sm:block">{pageTitle}</span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
        <div className="hidden lg:inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[rgba(13,38,34,0.6)] text-xs font-medium">
          <CalendarDays className="w-3.5 h-3.5" strokeWidth={1.75} />
          {today}
        </div>

        <button
          type="button"
          onClick={onOpenVoiceSimulator}
          className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md bg-white border border-[rgba(13,38,34,0.16)] hover:bg-[#F1F4EE] text-[#0D2622] text-xs font-medium transition-colors cursor-pointer"
        >
          <span className="relative flex items-center justify-center">
            <PhoneCall className="w-3.5 h-3.5 text-[#1E6B56]" strokeWidth={1.75} />
            <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-[#1E6B56] ring-2 ring-white" />
          </span>
          <span className="hidden md:inline">Voice AI Simulator</span>
          <span className="md:hidden">Test AI</span>
        </button>

        <button
          type="button"
          onClick={onOpenBooking}
          className="inline-flex items-center gap-1.5 h-8 px-2.5 sm:px-3 rounded-md bg-[#0D2622] hover:bg-[#143530] text-[#F1F4EE] text-xs font-medium transition-colors cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" strokeWidth={2} />
          <span className="hidden sm:inline">Book Appointment</span>
          <span className="sm:hidden">Intake</span>
        </button>

        <div className="w-px h-5 bg-[rgba(13,38,34,0.12)] mx-1" />

        <div className="relative">
          <button
            onClick={() => setIsProfileOpen(!isProfileOpen)}
            className="flex items-center gap-2 h-9 pl-1 pr-1.5 sm:pr-2 rounded-full hover:bg-[#F1F4EE] transition-colors cursor-pointer"
            aria-label="Account menu"
          >
            <Image
              src={activeRole === 'receptionist' ? APP_CONFIG.receptionistProfileIcon : APP_CONFIG.profileIcon}
              alt={doctorName}
              width={28}
              height={28}
              className="w-7 h-7 rounded-full object-cover bg-[#0D2622]"
            />
            <div className="hidden md:block text-left leading-tight max-w-[130px]">
              <p className="text-[12px] font-medium text-[#0D2622] truncate">{doctorName}</p>
              <p className="text-[10px] text-[rgba(13,38,34,0.6)] truncate">{specialty}</p>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-[rgba(13,38,34,0.4)] hidden sm:block" />
          </button>

          {isProfileOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setIsProfileOpen(false)} />
              <div className="absolute right-0 mt-2 w-52 bg-white rounded-xl shadow-lg border border-[rgba(13,38,34,0.12)] py-1.5 z-50 origin-top-right">
                <div className="px-3.5 py-2 border-b border-[rgba(13,38,34,0.08)]">
                  <p className="text-xs font-medium text-[#0D2622] truncate">{doctorName}</p>
                  <p className="text-[11px] text-[rgba(13,38,34,0.6)] truncate">{clinicName}</p>
                </div>
                {activeRole !== 'receptionist' && (
                  <div className="py-1">
                    <Link
                      href="/clinic/settings"
                      onClick={() => setIsProfileOpen(false)}
                      className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-medium text-[#0D2622] hover:bg-[#F1F4EE] transition-colors"
                    >
                      <Settings className="w-3.5 h-3.5 text-[rgba(13,38,34,0.5)]" strokeWidth={1.75} />
                      <span>Settings</span>
                    </Link>
                  </div>
                )}
                <div className="h-px bg-[rgba(13,38,34,0.08)] my-0.5" />
                <div className="py-0.5">
                  <button
                    type="button"
                    onClick={() => {
                      setIsProfileOpen(false);
                      onSignOut();
                    }}
                    className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors cursor-pointer"
                  >
                    <LogOut className="w-3.5 h-3.5 text-red-600" strokeWidth={1.75} />
                    <span>Sign out</span>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}