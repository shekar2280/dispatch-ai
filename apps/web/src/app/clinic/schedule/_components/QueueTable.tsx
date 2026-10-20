'use client';

import React from 'react';
import { Search, CalendarClock, Users } from 'lucide-react';
import { AppointmentItem, BillItem } from '../../types';
import { useClinicStore } from '../../store';
import { ScheduleTableRowsSkeleton } from '../../_components/ClinicSkeletons';
import { QueueRow } from './QueueRow';

interface QueueTableProps {
  isLoading: boolean;
  totalAppointmentsCount: number;
  activeTab: 'queue' | 'due' | 'completed' | 'all';
  setActiveTab: (tab: 'queue' | 'due' | 'completed' | 'all') => void;
  queueCount: number;
  expectedCount: number;
  completedCount: number;
  paymentDueCount: number;
  allCount: number;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  filteredAppointments: AppointmentItem[];
  activeQueueAppointments?: AppointmentItem[];
  expectedAppointments?: AppointmentItem[];
  completedAppointments?: AppointmentItem[];
  paymentDueAppointments?: AppointmentItem[];
  clinicTz: string;
  isToday: boolean;
  dateLabel: string;
  actionState: { id: string; action: 'arrive' | 'call' | 'complete' | 'skip' | 'reinsert' | 'move_tomorrow' } | null;
  collectingFeeId: string | null;
  setCollectingFeeId: (id: string | null) => void;
  activeMenuId: string | null;
  setActiveMenuId: (id: string | null) => void;
  onCollectFee: (payload: {
    appointmentId: string;
    paymentMethod?: 'Cash' | 'UPI';
    paymentStatus?: 'paid' | 'pending';
    fee?: number;
    billItems?: BillItem[];
    amountReceived?: number;
    reference?: string;
    idempotencyKey?: string;
    adjustmentReason?: string;
  }) => Promise<any> | void;
  isCollectingFee: boolean;
  onComplete: (id: string) => void;
  onCall: (id: string) => void;
  onSkip: (id: string) => void;
  onReinsert: (id: string) => void;
  onCheckIn: (item: AppointmentItem) => void;
  onReschedule: (item: AppointmentItem) => void;
  onBookReportReview: (item: AppointmentItem) => void;
  onCancel: (id: string) => void;
}

export function QueueTable({
  isLoading,
  totalAppointmentsCount,
  activeTab,
  setActiveTab,
  queueCount,
  expectedCount,
  completedCount,
  paymentDueCount,
  allCount,
  searchQuery,
  setSearchQuery,
  filteredAppointments,
  activeQueueAppointments = [],
  expectedAppointments = [],
  completedAppointments = [],
  paymentDueAppointments = [],
  clinicTz,
  isToday,
  dateLabel,
  actionState,
  collectingFeeId,
  setCollectingFeeId,
  activeMenuId,
  setActiveMenuId,
  onCollectFee,
  isCollectingFee,
  onComplete,
  onCall,
  onSkip,
  onReinsert,
  onCheckIn,
  onReschedule,
  onBookReportReview,
  onCancel,
}: QueueTableProps) {
  const activeRole = useClinicStore((s) => s.activeRole);
  const isDoctor = activeRole === 'doctor';
  const query = searchQuery.toLowerCase().trim();

  const filterItem = (item: AppointmentItem) => {
    if (!query) return true;
    return (
      item.patient_name.toLowerCase().includes(query) ||
      item.patient_phone.includes(query) ||
      (item.display_token || '').toLowerCase().includes(query) ||
      (item.appointment_time || '').toLowerCase().includes(query) ||
      (item.chief_complaint || '').toLowerCase().includes(query)
    );
  };

  const activeQueueItems = activeQueueAppointments.filter(filterItem);
  const expectedItems = expectedAppointments.filter(filterItem);
  const completedItems = completedAppointments.filter(filterItem);
  const dueItems = paymentDueAppointments.filter(filterItem);

  return (
    <div className="bg-white rounded-2xl border border-neutral-200 shadow-2xs w-full relative">
      <div className="p-3 sm:px-4 sm:py-3 border-b border-neutral-200/90 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-neutral-50/70 rounded-t-2xl">
        <div className="flex items-center p-0.5 rounded-xl bg-neutral-200/80 overflow-x-auto">
          {!isDoctor && (
            <button
              type="button"
              onClick={() => setActiveTab('due')}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap cursor-pointer flex items-center gap-1.5 ${activeTab === 'due' ? 'bg-white text-amber-900 font-semibold shadow-2xs' : 'text-neutral-600 hover:text-neutral-900'}`}
            >
              <span>Today’s Due</span>
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${activeTab === 'due' ? 'bg-amber-100 text-amber-900' : 'bg-neutral-300/60 text-neutral-700'}`}>{paymentDueCount}</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => setActiveTab('queue')}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'queue'
                ? 'bg-white text-neutral-950 font-semibold shadow-2xs'
                : 'text-neutral-600 hover:text-neutral-900'
            }`}
          >
            <span>Waiting Room</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${activeTab === 'queue' ? 'bg-neutral-100 text-neutral-900' : 'bg-neutral-300/60 text-neutral-700'}`}>
              {queueCount}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('completed')}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'completed'
                ? 'bg-white text-neutral-950 font-semibold shadow-2xs'
                : 'text-neutral-600 hover:text-neutral-900'
            }`}
          >
            <span>Completed</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${activeTab === 'completed' ? 'bg-neutral-100 text-neutral-900' : 'bg-neutral-300/60 text-neutral-700'}`}>
              {completedCount}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('all')}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all whitespace-nowrap cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'all'
                ? 'bg-white text-neutral-950 font-semibold shadow-2xs'
                : 'text-neutral-600 hover:text-neutral-900'
            }`}
          >
            <span>All Patients</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${activeTab === 'all' ? 'bg-neutral-100 text-neutral-900' : 'bg-neutral-300/60 text-neutral-700'}`}>
              {allCount}
            </span>
          </button>
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            placeholder="Search name, phone, or token..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1 rounded-xl border border-neutral-200 bg-white text-xs text-neutral-900 focus:outline-none focus:border-neutral-900 placeholder:text-neutral-400 transition-colors"
          />
        </div>
      </div>

      {activeTab === 'queue' ? (
        <div>
          <div>
            <div className="px-4 py-2 bg-neutral-50/60 border-b border-neutral-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-neutral-900 tracking-tight">
                  Checked-in Patients
                </span>
                <span className="text-[10px] font-mono font-medium px-2 py-0.2 rounded-full bg-neutral-200/80 text-neutral-800">
                  {activeQueueItems.length}
                </span>
              </div>
              <span className="text-[11px] font-normal text-neutral-400">
                Ready for consultation
              </span>
            </div>

            <div>
              {isLoading && totalAppointmentsCount === 0 ? (
                <ScheduleTableRowsSkeleton />
              ) : activeQueueItems.length === 0 ? (
                <div className="py-4 px-4 text-xs text-neutral-500 flex items-center justify-between bg-neutral-50/30 border-b border-neutral-100">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-neutral-400 shrink-0" />
                    <span className="font-semibold text-neutral-800">
                      {isToday ? 'Waiting room is currently clear' : `Consultations begin on ${dateLabel}`}
                    </span>
                    <span className="text-neutral-400 hidden sm:inline">
                      {isToday ? '— Check in patients from upcoming arrivals below' : ''}
                    </span>
                  </div>
                </div>
              ) : (
                activeQueueItems.map((item) => (
                  <QueueRow
                    key={item.id}
                    item={item}
                    clinicTz={clinicTz}
                    isToday={isToday}
                    actionState={actionState}
                    collectingFeeId={collectingFeeId}
                    setCollectingFeeId={setCollectingFeeId}
                    activeMenuId={activeMenuId}
                    setActiveMenuId={setActiveMenuId}
                    onCollectFee={onCollectFee}
                    isCollectingFee={isCollectingFee}
                    onComplete={onComplete}
                    onCall={onCall}
                    onSkip={onSkip}
                    onReinsert={onReinsert}
                    onCheckIn={onCheckIn}
                    onReschedule={onReschedule}
                    onBookReportReview={onBookReportReview}
                    onCancel={onCancel}
                  />
                ))
              )}
            </div>
          </div>

          {expectedItems.length > 0 && (
            <div>
              <div className="px-4 py-2.5 bg-neutral-50/60 border-y border-neutral-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-neutral-900 tracking-tight">
                    Upcoming Arrivals
                  </span>
                  <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-neutral-200/80 text-neutral-800">
                    {expectedItems.length}
                  </span>
                </div>
                <span className="text-[11px] font-medium text-neutral-400">
                  Scheduled for today
                </span>
              </div>

              <div>
                {expectedItems.map((item) => (
                  <QueueRow
                    key={item.id}
                    item={item}
                    clinicTz={clinicTz}
                    isToday={isToday}
                    actionState={actionState}
                    collectingFeeId={collectingFeeId}
                    setCollectingFeeId={setCollectingFeeId}
                    activeMenuId={activeMenuId}
                    setActiveMenuId={setActiveMenuId}
                    onCollectFee={onCollectFee}
                    isCollectingFee={isCollectingFee}
                    onComplete={onComplete}
                    onCall={onCall}
                    onSkip={onSkip}
                    onReinsert={onReinsert}
                    onCheckIn={onCheckIn}
                    onReschedule={onReschedule}
                    onBookReportReview={onBookReportReview}
                    onCancel={onCancel}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div>
          {isLoading && totalAppointmentsCount === 0 ? (
            <ScheduleTableRowsSkeleton />
          ) : filteredAppointments.length === 0 ? (
            <div className="py-12 text-center text-xs text-neutral-500 flex flex-col items-center justify-center gap-1.5">
              <CalendarClock className="w-6 h-6 text-neutral-300 mb-1" />
              <p className="font-semibold text-neutral-900">
                {activeTab === 'due' ? 'No completed visits have a balance due'
                  : activeTab === 'completed' ? 'No completed appointments recorded yet'
                    : 'No matching records found'}
              </p>
              <p className="text-neutral-500 text-[11px]">
                {activeTab === 'due'
                  ? 'Completed visits with unpaid balances will stay here until settled.'
                  : 'Appointments will appear here as they are processed.'}
              </p>
            </div>
          ) : (
            filteredAppointments.map((item) => (
              <QueueRow
                key={item.id}
                item={item}
                clinicTz={clinicTz}
                isToday={isToday}
                actionState={actionState}
                collectingFeeId={collectingFeeId}
                setCollectingFeeId={setCollectingFeeId}
                activeMenuId={activeMenuId}
                setActiveMenuId={setActiveMenuId}
                onCollectFee={onCollectFee}
                isCollectingFee={isCollectingFee}
                onComplete={onComplete}
                onCall={onCall}
                onSkip={onSkip}
                onReinsert={onReinsert}
                onCheckIn={onCheckIn}
                onReschedule={onReschedule}
                onBookReportReview={onBookReportReview}
                onCancel={onCancel}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
