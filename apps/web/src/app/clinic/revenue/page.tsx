'use client';

import React, { useMemo, useState } from 'react';
import {
  QrCode,
  Banknote,
  CheckCircle2,
  Clock,
  Receipt,
  Loader2,
  RefreshCw,
  Search,
  Calendar,
  AlertCircle,
  Sparkles,
  TrendingUp,
  Wallet,
  ArrowDownRight,
  ShieldCheck,
} from 'lucide-react';
import { useClinicStore } from '../store';
import { useClinicRevenueQuery, useClinicAppointmentsQuery } from '../_hooks/useClinicQueries';
import { useCollectClinicFeeMutation } from '../_hooks/useClinicMutations';
import { ActionConfirmModal } from '../_components/ActionConfirmModal';
import { RevenuePageSkeleton } from '../_components/ClinicSkeletons';
import QuickBillModal from '../_components/QuickBillModal';
import { ClinicRevenueTransactionItem } from '../types';

export default function ClinicRevenuePage() {
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'week' | 'month' | 'all'>('today');
  const [collectingKey, setCollectingKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'pending' | 'settled'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [methodFilter, setMethodFilter] = useState<'all' | 'UPI' | 'Cash'>('all');
  const [billModalTx, setBillModalTx] = useState<ClinicRevenueTransactionItem | null>(null);
  const [pendingCollection, setPendingCollection] = useState<{
    appointmentId: string;
    method: 'UPI' | 'Cash';
    patientName: string;
    amount: number;
  } | null>(null);

  const orgId = useClinicStore((s) => s.orgId);
  const activeRole = useClinicStore((s) => s.activeRole);
  const isReceptionist = activeRole === 'receptionist';
  const {
    data: clinicRevenueData,
    isLoading: isRevenueLoading,
    isRefetching,
    refetch,
  } = useClinicRevenueQuery(orgId, selectedPeriod);
  const collectFeeMutation = useCollectClinicFeeMutation(orgId);
  const { data: visits = [], isLoading: visitsLoading, error: visitsError } = useClinicAppointmentsQuery(orgId);
  const checkedInVisitIds = useMemo(() => new Set(visits.filter((visit) =>
    Boolean(visit.checked_in_at) || ['arrived', 'in_progress', 'completed'].includes(visit.status)
  ).map((visit) => visit.id)), [visits]);

  const handleCollect = async (appointmentId: string, method: 'UPI' | 'Cash') => {
    setCollectingKey(`${appointmentId}-${method}`);
    try {
      await collectFeeMutation.mutateAsync({ appointmentId, paymentMethod: method });
    } finally {
      setCollectingKey(null);
      setPendingCollection(null);
    }
  };

  const totalSettled = clinicRevenueData?.total_settled || 0;
  const upiTotal = clinicRevenueData?.upi_total || 0;
  const cashTotal = clinicRevenueData?.cash_total || 0;
  const transactions = useMemo(() => clinicRevenueData?.transactions ?? [], [clinicRevenueData?.transactions]);
  const currencySymbol = clinicRevenueData?.currency_symbol || '';
  // Estimated booking fees become payable only after the patient arrives.
  const totalPending = transactions.filter((tx) => tx.status === 'pending' && checkedInVisitIds.has(tx.id))
    .reduce((sum, tx) => sum + Math.max(0, tx.balance_due ?? tx.fee_amount - (tx.amount_paid ?? 0)), 0);

  const settledCount = useMemo(() => transactions.filter((t) => t.status === 'settled').length, [transactions]);
  const pendingCount = useMemo(() => transactions.filter((t) => t.status === 'pending' && checkedInVisitIds.has(t.id)).length, [transactions, checkedInVisitIds]);
  const collectionRate = useMemo(() => {
    const total = totalSettled + totalPending;
    return total > 0 ? Math.round((totalSettled / total) * 100) : 0;
  }, [totalSettled, totalPending]);

  const filteredTransactions = useMemo(() => {
    return transactions.filter((tx) => {
      if (activeTab === 'pending' && (tx.status !== 'pending' || !checkedInVisitIds.has(tx.id))) return false;
      if (activeTab === 'settled' && tx.status !== 'settled') return false;
      if (methodFilter !== 'all' && tx.payment_method !== methodFilter && tx.status === 'settled') return false;

      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase().trim();
      return (
        tx.patient_name.toLowerCase().includes(q) ||
        tx.patient_phone.includes(q) ||
        (tx.appointment_time || '').toLowerCase().includes(q) ||
        (tx.appointment_date || '').toLowerCase().includes(q) ||
        (tx.source || '').toLowerCase().includes(q)
      );
    });
  }, [transactions, activeTab, methodFilter, searchQuery, checkedInVisitIds]);

  const periodLabel =
    selectedPeriod === 'today'
      ? 'Today'
      : selectedPeriod === 'week'
      ? 'This Week'
      : selectedPeriod === 'month'
      ? 'This Month'
      : 'All Time';

  return (
    <div className="w-full space-y-4 pb-24 lg:pb-12 text-neutral-900">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-neutral-950">
            {isReceptionist ? 'Patient Billing & Fee Collection' : 'Revenue Desk'}
          </h1>
          <p className="text-xs text-neutral-500 mt-0.5 font-normal">
            {isReceptionist
              ? 'Collect visit fees, record medicines and procedures, and manage patient receipts'
              : 'Real-time fee collection, payments, and daily cash tracking'}
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-center">
          <div className="flex items-center p-0.5 rounded-lg bg-neutral-200/70">
            {(['today', 'week', 'month', 'all'] as const).map((period) => (
              <button
                key={period}
                type="button"
                onClick={() => setSelectedPeriod(period)}
                className={`px-3 py-1 rounded-md text-xs font-semibold capitalize transition-all whitespace-nowrap ${
                  selectedPeriod === period
                    ? 'bg-white text-neutral-900 shadow-2xs'
                    : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                {period === 'today' ? 'Today' : period === 'week' ? 'Week' : period === 'month' ? 'Month' : 'All Time'}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="p-1.5 rounded-lg bg-white border border-neutral-200 text-neutral-600 hover:text-black hover:bg-neutral-50 transition-colors shadow-2xs disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {isRevenueLoading && !clinicRevenueData ? (
        <RevenuePageSkeleton />
      ) : (
        <>
          {isReceptionist ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Awaiting payment</span>
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-amber-900 tracking-tight">{pendingCount}</span>
                  <span className="text-[10px] text-amber-700 font-semibold">visits</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500">
                  Checked-in visits only
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Settled Visits</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-neutral-900 tracking-tight">{settledCount}</span>
                  <span className="text-[10px] text-emerald-600 font-semibold">{collectionRate}% complete</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500">
                  Receipts cleared
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Total Patients</span>
                  <Receipt className="w-3.5 h-3.5 text-neutral-400" />
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-neutral-900 tracking-tight">{transactions.length}</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500">
                  In records for {periodLabel}
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Front Desk Mode</span>
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-sm font-bold text-emerald-900">Direct Billing</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500">
                  Instant receipt collection
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Collected ({periodLabel})</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-neutral-900 tracking-tight">{currencySymbol}{totalSettled}</span>
                  <span className="text-[10px] text-emerald-600 font-semibold">{collectionRate}% rate</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 flex items-center justify-between text-[10px] text-neutral-500">
                  <span>UPI: {currencySymbol}{upiTotal}</span>
                  <span>Cash: {currencySymbol}{cashTotal}</span>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Outstanding balance</span>
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-amber-900 tracking-tight">{visitsLoading || visitsError ? '—' : `${currencySymbol}${totalPending}`}</span>
                  <span className="text-[10px] text-amber-700 font-semibold">{pendingCount} patients</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500 truncate">
                  Checked-in visits only · Bookings excluded
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Drawer Cash</span>
                  <Banknote className="w-3.5 h-3.5 text-neutral-400" />
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-neutral-900 tracking-tight">{currencySymbol}{cashTotal}</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500">
                  Cash in drawer
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white border border-neutral-200 shadow-2xs">
                <div className="flex items-center justify-between text-neutral-500 text-[11px] font-semibold mb-1">
                  <span>Digital (UPI)</span>
                  <QrCode className="w-3.5 h-3.5 text-neutral-400" />
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-neutral-900 tracking-tight">{currencySymbol}{upiTotal}</span>
                </div>
                <div className="mt-2 pt-2 border-t border-neutral-100 text-[10px] text-neutral-500">
                  Received via UPI / Online
                </div>
              </div>
            </div>
          )}

      <div className="bg-white rounded-xl border border-neutral-200 shadow-2xs overflow-hidden w-full">
        <div className="px-4 py-2.5 border-b border-neutral-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-neutral-50/60">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center p-0.5 rounded-lg bg-neutral-200/70 overflow-x-auto">
              <button
                type="button"
                onClick={() => setActiveTab('all')}
                className={`px-3.5 py-1 rounded-md text-xs font-semibold transition-all whitespace-nowrap ${
                  activeTab === 'all'
                    ? 'bg-white text-neutral-900 shadow-2xs'
                    : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                All ({transactions.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('pending')}
                className={`px-3.5 py-1 rounded-md text-xs font-semibold transition-all whitespace-nowrap flex items-center gap-1.5 ${
                  activeTab === 'pending'
                    ? 'bg-white text-neutral-900 shadow-2xs'
                    : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                {pendingCount > 0 && <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>}
                Awaiting payment ({pendingCount})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('settled')}
                className={`px-3.5 py-1 rounded-md text-xs font-semibold transition-all whitespace-nowrap ${
                  activeTab === 'settled'
                    ? 'bg-white text-neutral-900 shadow-2xs'
                    : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                Settled ({settledCount})
              </button>
            </div>

            <div className="flex items-center bg-neutral-100 p-0.5 rounded-lg border border-neutral-200/80 text-[11px]">
              {(['all', 'UPI', 'Cash'] as const).map((method) => (
                <button
                  key={method}
                  type="button"
                  onClick={() => setMethodFilter(method)}
                  className={`px-2 py-0.5 rounded font-medium transition-all ${
                    methodFilter === method ? 'bg-white text-neutral-900 font-semibold shadow-2xs' : 'text-neutral-500 hover:text-neutral-900'
                  }`}
                >
                  {method === 'all' ? 'All Methods' : method}
                </button>
              ))}
            </div>
          </div>

          <div className="relative w-full sm:w-72">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-400" />
            <input
              type="text"
              placeholder="Search by patient, phone, date..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-2.5 py-1 rounded-lg border border-neutral-200 bg-white text-xs text-neutral-900 focus:outline-none focus:border-neutral-900 placeholder:text-neutral-400"
            />
          </div>
        </div>

        <div className="hidden md:grid grid-cols-12 px-4 py-2 bg-neutral-50/90 border-b border-neutral-100 text-[10px] font-bold uppercase tracking-wider text-neutral-400">
          <div className="col-span-2">Date & Time</div>
          <div className="col-span-3">Patient</div>
          <div className="col-span-2">Source / Type</div>
          <div className="col-span-2">Payment Status</div>
          <div className="col-span-1">Amount</div>
          <div className="col-span-2 text-right">Settlement Action</div>
        </div>

        <div className="divide-y divide-neutral-100">
          {filteredTransactions.map((tx) => {
            const isSettled = tx.status === 'settled';
            const isPending = tx.status === 'pending' && checkedInVisitIds.has(tx.id);
            const canBill = isSettled || checkedInVisitIds.has(tx.id);

            return (
              <div
                key={tx.id}
                className={`px-4 py-2.5 transition-colors flex flex-col md:grid md:grid-cols-12 md:items-center gap-2 md:gap-0 text-xs ${
                  isPending ? 'bg-amber-50/20 hover:bg-amber-50/40' : 'hover:bg-neutral-50/60'
                }`}
              >
                <div className="col-span-2 flex flex-col justify-center min-w-0 pr-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono font-bold text-[11px] px-2 py-0.5 rounded-md border bg-neutral-100 text-neutral-800 border-neutral-200 shrink-0">
                      {tx.appointment_time || 'Clinic'}
                    </span>
                    <span className="text-[10px] text-neutral-500 font-mono">
                      {tx.appointment_date}
                    </span>
                  </div>
                  {isSettled && tx.collected_at && (
                    <div className="flex items-center gap-1 mt-1 text-[10px] text-emerald-700 font-medium truncate">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
                      <span className="truncate">Paid: {tx.collected_at}</span>
                    </div>
                  )}
                </div>

                <div className="col-span-3 min-w-0 pr-3">
                  <p className="font-semibold text-xs text-neutral-900 truncate">
                    {tx.patient_name}
                  </p>
                  <span className="font-mono text-[11px] text-neutral-400 block truncate">
                    {tx.patient_phone || 'No phone'}
                  </span>
                </div>

                <div className="col-span-2 min-w-0 pr-2 flex items-center gap-1.5">
                  <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-neutral-100 text-neutral-700 border border-neutral-200/80 capitalize">
                    {tx.source === 'ai_voice' ? 'Booked by Tulsi' : tx.source === 'walk_in' ? 'Walk-in' : 'Appointment'}
                  </span>
                  {tx.source === 'ai_voice' && (
                    <Sparkles className="w-3.5 h-3.5 text-neutral-600 shrink-0" />
                  )}
                </div>

                <div className="col-span-2 flex items-center">
                  {isSettled ? (
                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                      Settled ({tx.payment_method})
                    </span>
                  ) : !canBill ? (
                    <span className="inline-flex items-center rounded-full border border-neutral-200 bg-neutral-50 px-2 py-0.5 text-[10px] font-medium text-neutral-500">
                      {visitsLoading ? 'Checking arrival…' : visitsError ? 'Arrival status unavailable' : 'Awaiting check-in'}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-900 border border-amber-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                      Awaiting payment
                    </span>
                  )}
                </div>

                <div className="col-span-1">
                  {!canBill && <span className="mb-0.5 block text-[10px] text-neutral-400">Estimated fee</span>}
                  <div className="flex items-center gap-1.5">
                    <span className={`text-xs font-bold ${isSettled ? 'text-neutral-900' : 'text-amber-900'}`}>
                      {currencySymbol}{tx.fee_amount}
                    </span>
                    {tx.bill_items && tx.bill_items.length > 0 && (
                      <span className="text-[9px] px-1 py-0.2 rounded bg-neutral-100 text-neutral-600 border border-neutral-200" title={tx.bill_items.map(b => `${b.name}: ${currencySymbol}${b.amount}`).join(', ')}>
                        {tx.bill_items.length} items
                      </span>
                    )}
                  </div>
                </div>

                <div className="col-span-2 flex items-center justify-end gap-1.5">
                  {canBill ? <>
                  <button
                    type="button"
                    onClick={() => setBillModalTx(tx)}
                    className="h-7 px-2 rounded-lg border border-neutral-200 hover:bg-neutral-100 text-neutral-700 text-[11px] font-semibold flex items-center gap-1 transition-all cursor-pointer"
                    title="Itemize medicines or test charges"
                  >
                    <Receipt className="w-3 h-3 text-neutral-500" />
                    <span>{isSettled ? 'View' : 'Bill'}</span>
                  </button>

                  {isSettled ? (
                    <div className="text-right flex flex-col items-end">
                      <span className="text-[11px] font-semibold text-emerald-800 flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 border border-emerald-200/90">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        {tx.collected_at || 'Settled'}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={collectingKey?.startsWith(`${tx.id}-`)}
                        onClick={() =>
                          setPendingCollection({
                            appointmentId: tx.id,
                            method: 'Cash',
                            patientName: tx.patient_name,
                            amount: tx.fee_amount,
                          })
                        }
                        className="h-7 px-2.5 rounded-lg border border-neutral-200 hover:bg-neutral-100 text-neutral-800 text-[11px] font-semibold flex items-center gap-1 transition-all disabled:opacity-60 cursor-pointer"
                      >
                        {collectingKey === `${tx.id}-Cash` ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Banknote className="w-3 h-3 text-neutral-600" />
                        )}
                        <span>Cash</span>
                      </button>

                      <button
                        type="button"
                        disabled={collectingKey?.startsWith(`${tx.id}-`)}
                        onClick={() =>
                          setPendingCollection({
                            appointmentId: tx.id,
                            method: 'UPI',
                            patientName: tx.patient_name,
                            amount: tx.fee_amount,
                          })
                        }
                        className="h-7 px-2.5 rounded-lg bg-neutral-900 hover:bg-black text-white text-[11px] font-semibold flex items-center gap-1 transition-all disabled:opacity-60 shadow-2xs cursor-pointer"
                      >
                        {collectingKey === `${tx.id}-UPI` ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <QrCode className="w-3 h-3" />
                        )}
                        <span>UPI</span>
                      </button>
                    </div>
                  )}
                  </> : <span className="text-[11px] text-neutral-400">Available after check-in</span>}
                </div>
              </div>
            );
          })}

          {filteredTransactions.length === 0 && (
            <div className="py-12 text-center text-xs text-neutral-500 flex flex-col items-center justify-center gap-1.5">
              <Receipt className="w-6 h-6 text-neutral-300 mb-1" />
              <p className="font-semibold text-neutral-800">
                {activeTab === 'pending'
                  ? 'No pending receivables'
                  : activeTab === 'settled'
                  ? 'No settled payments found'
                  : 'No transaction records found'}
              </p>
              <p className="text-neutral-400 text-[11px]">
                {activeTab === 'pending'
                  ? 'No checked-in visits are awaiting payment in this view.'
                  : 'Adjust the period or search filters to view records.'}
              </p>
            </div>
          )}
        </div>
      </div>



      <ActionConfirmModal
        isOpen={!!pendingCollection}
        title={pendingCollection?.method === 'Cash' ? 'Confirm Cash Collection' : 'Confirm UPI Settlement'}
        description={`Record ${currencySymbol}${pendingCollection?.amount} as collected via ${pendingCollection?.method} for ${pendingCollection?.patientName}? This records the fee as collected and updates today's collection total.`}
        confirmLabel={pendingCollection?.method === 'Cash' ? 'Confirm Cash Received' : 'Confirm UPI Verified'}
        variant={pendingCollection?.method === 'Cash' ? 'amber' : 'emerald'}
        isSubmitting={Boolean(collectingKey && pendingCollection && collectingKey.startsWith(`${pendingCollection.appointmentId}-`))}
        onConfirm={() => {
          if (pendingCollection) {
            handleCollect(pendingCollection.appointmentId, pendingCollection.method);
          }
        }}
        onClose={() => {
          if (!collectingKey) {
            setPendingCollection(null);
          }
        }}
      />

      {billModalTx && (
        <QuickBillModal
          isOpen={Boolean(billModalTx)}
          onClose={() => setBillModalTx(null)}
          patientName={billModalTx.patient_name}
          patientPhone={billModalTx.patient_phone}
          initialFee={billModalTx.fee_amount}
          initialPaymentStatus={billModalTx.status === 'settled' ? 'paid' : 'pending'}
          initialPaymentMethod={billModalTx.payment_method}
          initialBillItems={billModalTx.bill_items || []}
          onCollect={async (payload) => {
            await collectFeeMutation.mutateAsync({
              appointmentId: billModalTx.id,
              paymentMethod: payload.paymentMethod,
              paymentStatus: payload.paymentStatus,
              fee: payload.fee,
              billItems: payload.billItems,
            });
            refetch();
          }}
          isSubmitting={collectFeeMutation.isPending}
        />
      )}
        </>
      )}
    </div>
  );
}