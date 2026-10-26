'use client';

import React from 'react';
import Link from 'next/link';
import {
  CheckCircle2,
  Clock,
  Loader2,
  MoreHorizontal,
  UserCheck,
  Banknote,
  QrCode,
  Sparkles,
  User,
  Calendar,
  Trash2,
  Receipt,
} from 'lucide-react';
import { AppointmentItem, BillItem } from '../../types';
import { useClinicStore } from '../../store';
import { AuditTimelineModal } from './AuditTimelineModal';
import QuickBillModal from '../../_components/QuickBillModal';
import { formatClinicTime } from '../_utils/timeUtils';
import { useClinicBillingCatalogQuery } from '../../_hooks/useClinicQueries';

interface QueueRowProps {
  item: AppointmentItem;
  clinicTz: string;
  isToday: boolean;
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

export function QueueRow({
  item,
  isToday,
  clinicTz,
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
}: QueueRowProps) {
  const isArrived = item.status === 'arrived';
  const isInProgress = item.status === 'in_progress';
  const isCompleted = item.status === 'completed';
  const isSkipped = item.status === 'skipped';
  const isCancelled = item.status === 'cancelled';
  const isScheduled = !isArrived && !isInProgress && !isCompleted && !isSkipped && !isCancelled;
  const isPaid = item.payment_status === 'paid';
  const activeRole = useClinicStore((s) => s.activeRole);
  const orgId = useClinicStore((s) => s.orgId);
  const { data: billingCatalog } = useClinicBillingCatalogQuery(orgId);
  const currencySymbol = billingCatalog?.currency_symbol || '';
  const isDoctor = activeRole === 'doctor';
  const isReceptionist = activeRole === 'receptionist';
  const hasBalanceDue = (item.balance_due ?? (isPaid ? 0 : (item.fee ?? 0))) > 0;
  const completedPaymentDue = isCompleted && !isPaid && hasBalanceDue;
  const isMenuOpen = activeMenuId === item.id;
  const isFeeOpen = collectingFeeId === item.id;
  const [isAuditModalOpen, setIsAuditModalOpen] = React.useState(false);
  const [isQuickBillOpen, setIsQuickBillOpen] = React.useState(false);

  return (
    <div
      className={`px-4 py-3 transition-all flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs border-b border-neutral-100 last:border-b-0 hover:bg-[#FAF9F6]/60 ${
        isMenuOpen ? 'relative z-30' : ''
      } ${
        completedPaymentDue
          ? 'bg-amber-100/70 border-l-4 border-l-orange-500'
          : isInProgress
          ? 'bg-amber-50/40 border-l-4 border-l-amber-500'
          : isArrived
            ? 'bg-emerald-50/20 border-l-4 border-l-emerald-500'
            : isCompleted
              ? 'bg-neutral-50/30'
              : ''
      }`}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="w-16 sm:w-20 shrink-0 flex flex-col items-center justify-center py-1 px-1.5 rounded-lg bg-neutral-100/80 border border-neutral-200/60 text-center">
          <span className="font-mono font-semibold text-[11px] text-neutral-800 leading-tight">
            {item.appointment_time || 'Walk-in'}
          </span>
          <span className="text-[9.5px] font-medium text-neutral-500 font-mono mt-0.5">
            {item.display_token || (item.source === 'walk_in' ? 'Walk-in' : 'Slot')}
          </span>
        </div>

        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href={`/clinic/patients?${item.patient_id ? `id=${item.patient_id}&` : ''}name=${encodeURIComponent(item.patient_name)}&phone=${encodeURIComponent(item.patient_phone || '')}`}
              className={`font-semibold text-xs sm:text-[13px] truncate hover:text-black transition-colors cursor-pointer ${
                isCompleted ? 'text-neutral-600' : 'text-neutral-900'
              }`}
            >
              {item.patient_name}
            </Link>
            <span className="font-mono text-[11px] text-neutral-400">
              {item.patient_phone}
            </span>
            {item.source === 'ai_voice' && (
              <span className="inline-flex items-center gap-1 text-[9.5px] font-medium text-neutral-700 bg-neutral-100 px-2 py-0.2 rounded-full border border-neutral-200/80">
                <Sparkles className="w-2.5 h-2.5 text-neutral-600" />
                <span>Booked by Tulsi</span>
              </span>
            )}
            {item.urgency_reason && (
              <span title={item.urgency_reason} className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.2 text-[9.5px] font-medium text-amber-900">
                Staff-confirmed urgent
              </span>
            )}
            {item.token_prefix === 'R' && (
              <span className="text-[9.5px] font-medium text-purple-700 bg-purple-50 px-2 py-0.2 rounded-full border border-purple-200">
                Rollover
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-[11px] text-neutral-500 flex-wrap">
            <span className="truncate max-w-[280px] font-normal text-neutral-500">
              {item.chief_complaint || 'General Consultation'}
            </span>
            {item.checked_in_at && (
              <>
                <span className="text-neutral-300">•</span>
                <span className="text-neutral-400 font-mono text-[10.5px]">
                  Checked in {formatClinicTime(item.checked_in_at, clinicTz)}
                </span>
              </>
            )}
            {item.actual_duration_seconds ? (
              <>
                <span className="text-neutral-300">•</span>
                <span className="font-mono text-[10.5px] text-neutral-400">
                  Duration {Math.max(1, Math.round(item.actual_duration_seconds / 60))}m
                </span>
              </>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
        <div>
          {isInProgress ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-900 border border-amber-200/80">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              In Consultation
            </span>
          ) : isArrived ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200/80">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse" />
              Waiting
            </span>
          ) : isSkipped ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-neutral-100 text-neutral-600 border border-neutral-200">
              On Hold
            </span>
          ) : isCompleted ? (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${completedPaymentDue ? 'text-orange-900 bg-orange-100 border-orange-300' : 'text-neutral-600 bg-neutral-100 border-neutral-200'}`}>
              <CheckCircle2 className={`w-3 h-3 ${completedPaymentDue ? 'text-orange-700' : 'text-neutral-600'}`} />
              <span>Completed</span>
            </span>
          ) : isCancelled ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium text-rose-600 bg-rose-50 border border-rose-200">
              Cancelled
            </span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium text-neutral-600 bg-neutral-100 border border-neutral-200">
              Scheduled
            </span>
          )}
        </div>

        <div className="relative">
          {isPaid ? (
            <button
              type="button"
              onClick={() => setIsQuickBillOpen(true)}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100/80 border border-emerald-200 transition-colors cursor-pointer"
              title="Click to view or edit itemized bill"
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              <span>Paid</span>
            </button>
          ) : item.status === "completed" ? (
            isReceptionist ? (
              <button
                type="button"
                onClick={() => setIsQuickBillOpen(true)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-300 transition-colors cursor-pointer shadow-2xs"
                title="Click to itemize medicines, revisits, and collect payment"
              >
                <Banknote className="w-3 h-3 text-amber-700" />
                <span>{currencySymbol}{item.balance_due ?? item.fee ?? 0} Due</span>
              </button>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium text-amber-800 bg-amber-50 border border-amber-200">
                <Banknote className="w-3 h-3 text-amber-600" />
                <span>{currencySymbol}{item.balance_due ?? item.fee ?? 0} Due</span>
              </span>
            )
          ) : null}
        </div>

        {isToday && isInProgress && (
          isDoctor ? (
            <button
              type="button"
              onClick={() => onComplete(item.id)}
              disabled={actionState?.id === item.id}
              className="h-7 px-3 rounded-lg bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-medium flex items-center gap-1.5 transition-all disabled:opacity-60 shadow-xs cursor-pointer active:scale-95"
            >
              {actionState?.id === item.id && actionState.action === 'complete' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              )}
              <span>End</span>
            </button>
          ) : (
            <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 text-[11px] font-medium">
              In Consultation
            </span>
          )
        )}

        {isToday && isArrived && (
          <div className="flex items-center gap-1.5">
            {isDoctor ? (
              <>
                <button
                  type="button"
                  onClick={() => onCall(item.id)}
                  disabled={actionState?.id === item.id}
                  className="h-7 px-3 rounded-lg bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-medium flex items-center gap-1.5 transition-all disabled:opacity-60 shadow-xs cursor-pointer active:scale-95"
                >
                  {actionState?.id === item.id && actionState.action === 'call' ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <UserCheck className="w-3 h-3" />
                  )}
                  <span>Call In</span>
                </button>

                <button
                  type="button"
                  onClick={() => onSkip(item.id)}
                  disabled={actionState?.id === item.id}
                  title="Patient temporarily stepped out"
                  className="h-7 px-2.5 rounded-lg border border-neutral-200 hover:bg-neutral-100 text-neutral-600 text-xs font-medium transition-colors cursor-pointer"
                >
                  {actionState?.id === item.id && actionState.action === 'skip' ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    'Step Out'
                  )}
                </button>
              </>
            ) : (
              <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-medium">
                Waiting
              </span>
            )}
          </div>
        )}

        {isToday && isSkipped && (
          <button
            type="button"
            onClick={() => onReinsert(item.id)}
            disabled={actionState?.id === item.id}
            className="h-7 px-3 rounded-lg bg-purple-50 border border-purple-200 hover:bg-purple-100 text-purple-700 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            {actionState?.id === item.id && actionState.action === 'reinsert' ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              'Re-enter'
            )}
          </button>
        )}

        {isScheduled && isToday && (
          <button
            type="button"
            onClick={() => onCheckIn(item)}
            className="h-7 px-3 rounded-lg bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-medium flex items-center gap-1.5 transition-all shadow-xs cursor-pointer active:scale-95"
          >
            <UserCheck className="w-3 h-3" />
            <span>Check In</span>
          </button>
        )}

        <div className={`relative ${isMenuOpen ? 'z-40' : ''}`}>
          <button
            type="button"
            onClick={() => setActiveMenuId(isMenuOpen ? null : item.id)}
            className={`h-7 w-7 flex items-center justify-center rounded-lg border border-neutral-200 hover:border-neutral-300 hover:bg-neutral-100 text-neutral-600 hover:text-neutral-950 transition-all cursor-pointer ${
              isMenuOpen ? 'bg-neutral-100 border-neutral-400 text-neutral-950 ring-2 ring-neutral-900/10' : ''
            }`}
            title="More options"
          >
            <MoreHorizontal className="w-3.5 h-3.5" />
          </button>

          {isMenuOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setActiveMenuId(null)}
              />
              <div className="absolute right-0 top-full mt-1.5 z-50 bg-white border border-neutral-200 rounded-xl p-1 shadow-xl flex flex-col min-w-[168px] animate-in fade-in zoom-in-95 duration-150">
                <div className="space-y-0.5">
                  <Link
                    href={`/clinic/patients?${item.patient_id ? `id=${item.patient_id}&` : ''}name=${encodeURIComponent(item.patient_name)}&phone=${encodeURIComponent(item.patient_phone || '')}`}
                    onClick={() => setActiveMenuId(null)}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs font-medium text-neutral-700 hover:text-neutral-950 hover:bg-neutral-100 rounded-lg transition-colors"
                  >
                    <User className="w-3.5 h-3.5 text-neutral-500" />
                    <span>Patient history</span>
                  </Link>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveMenuId(null);
                      setIsAuditModalOpen(true);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-xs font-medium text-neutral-700 hover:text-neutral-950 hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
                  >
                    <Clock className="w-3.5 h-3.5 text-neutral-500" />
                    <span>Visit details</span>
                  </button>

                  {!isCompleted && !isCancelled && (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveMenuId(null);
                        onReschedule(item);
                      }}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-xs font-medium text-neutral-700 hover:text-neutral-950 hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
                    >
                      <Calendar className="w-3.5 h-3.5 text-neutral-500" />
                      <span>Reschedule</span>
                    </button>
                  )}

                  {isCompleted && (
                    <button
                      type="button"
                      onClick={() => onBookReportReview(item)}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-xs font-medium text-neutral-700 hover:text-neutral-950 hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
                    >
                      <Calendar className="w-3.5 h-3.5 text-neutral-500" />
                      <span>Book report review</span>
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => {
                      setActiveMenuId(null);
                      setIsQuickBillOpen(true);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-xs font-medium text-neutral-700 hover:text-neutral-950 hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
                  >
                    <Receipt className="w-3.5 h-3.5 text-neutral-500" />
                    <span>{isPaid ? 'View bill' : 'Create bill'}</span>
                  </button>
                </div>

                {!isCompleted && !isCancelled && (
                  <>
                    <div className="my-1 border-t border-neutral-100" />
                    <button
                      type="button"
                      onClick={() => {
                        setActiveMenuId(null);
                        onCancel(item.id);
                      }}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-xs font-medium text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-rose-500" />
                      <span>Cancel appointment</span>
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <AuditTimelineModal
        isOpen={isAuditModalOpen}
        appointment={item}
        onClose={() => setIsAuditModalOpen(false)}
        clinicTz={clinicTz}
      />

      <QuickBillModal
        isOpen={isQuickBillOpen}
        onClose={() => setIsQuickBillOpen(false)}
        patientName={item.patient_name}
        patientPhone={item.patient_phone}
        initialFee={item.fee ?? 0}
        initialPaymentStatus={item.payment_status}
        initialPaymentMethod={item.payment_method}
        initialBillItems={item.bill_items || []}
        initialAmountPaid={item.amount_paid || 0}
        paymentReceipts={item.payment_receipts || []}
        onCollect={async (payload) => {
          await onCollectFee({
            appointmentId: item.id,
            paymentMethod: payload.paymentMethod,
            paymentStatus: payload.paymentStatus,
            fee: payload.fee,
            billItems: payload.billItems,
            amountReceived: payload.amountReceived,
            reference: payload.reference,
            idempotencyKey: payload.idempotencyKey,
            adjustmentReason: payload.adjustmentReason,
          });
        }}
        isSubmitting={isCollectingFee}
      />
    </div>
  );
}
