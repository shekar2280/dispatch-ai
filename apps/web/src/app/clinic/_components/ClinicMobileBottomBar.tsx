'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  CalendarClock,
  Users,
  Inbox,
  PlusCircle,
  Receipt,
} from 'lucide-react';
import { useClinicStore } from '../store';

export function ClinicMobileBottomBar() {
  const pathname = usePathname();
  const activeRole = useClinicStore((s) => s.activeRole);
  const setBookingModalOpen = useClinicStore((s) => s.setBookingModalOpen);
  const setBookingModalType = useClinicStore((s) => s.setBookingModalType);

  const isNavActive = (href: string) =>
    href === '/clinic' ? pathname === '/clinic' : pathname.startsWith(href);

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 bg-[#F1F4EE]/95 backdrop-blur-md border-t border-[rgba(13,38,34,0.14)] shadow-[0_-4px_16px_rgba(13,38,34,0.06)] px-2 py-1.5 flex items-center justify-around safe-area-bottom">
      {activeRole === 'doctor' && (
        <Link
          href="/clinic"
          className={`flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition-all ${
            isNavActive('/clinic')
              ? 'text-[#0D2622] font-semibold bg-[#E3EBE0]'
              : 'text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] font-medium'
          }`}
        >
          <LayoutDashboard className="w-4 h-4 mb-0.5" />
          <span className="text-[10px] tracking-tight">Chamber</span>
        </Link>
      )}

      <Link
        href="/clinic/schedule"
        className={`flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition-all ${
          isNavActive('/clinic/schedule')
            ? 'text-[#0D2622] font-semibold bg-[#E3EBE0]'
            : 'text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] font-medium'
        }`}
      >
        <CalendarClock className="w-4 h-4 mb-0.5" />
        <span className="text-[10px] tracking-tight">Queue</span>
      </Link>

      <button
        type="button"
        onClick={() => {
          setBookingModalType('Pre-booked');
          setBookingModalOpen(true);
        }}
        className="flex flex-col items-center justify-center -mt-4 py-1 px-3.5 rounded-2xl bg-[#0D2622] text-[#F1F4EE] shadow-md active:scale-95 transition-all cursor-pointer border border-[rgba(13,38,34,0.2)]"
      >
        <PlusCircle className="w-5 h-5 text-[#F4B63A]" />
        <span className="text-[9px] font-extrabold uppercase tracking-wider text-[#F4B63A] mt-0.5">
          Book
        </span>
      </button>

      <Link
        href="/clinic/patients"
        className={`flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition-all ${
          isNavActive('/clinic/patients')
            ? 'text-[#0D2622] font-semibold bg-[#E3EBE0]'
            : 'text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] font-medium'
        }`}
      >
        <Users className="w-4 h-4 mb-0.5" />
        <span className="text-[10px] tracking-tight">Patients</span>
      </Link>

      {activeRole === 'doctor' ? (
        <Link
          href="/clinic/revenue"
          className={`flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition-all ${
            isNavActive('/clinic/revenue')
              ? 'text-[#0D2622] font-semibold bg-[#E3EBE0]'
              : 'text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] font-medium'
          }`}
        >
          <Receipt className="w-4 h-4 mb-0.5" />
          <span className="text-[10px] tracking-tight">Billing</span>
        </Link>
      ) : (
        <Link
          href="/clinic/action-center"
          className={`flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition-all ${
            isNavActive('/clinic/action-center')
              ? 'text-[#0D2622] font-semibold bg-[#E3EBE0]'
              : 'text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] font-medium'
          }`}
        >
          <Inbox className="w-4 h-4 mb-0.5" />
          <span className="text-[10px] tracking-tight">Urgent</span>
        </Link>
      )}
    </nav>
  );
}
