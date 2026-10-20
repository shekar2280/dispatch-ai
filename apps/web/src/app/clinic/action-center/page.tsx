'use client';

import React, { useState } from 'react';
import {
  Phone,
  CheckCircle2,
  FileCheck,
  Check,
  Loader2,
} from 'lucide-react';
import { useClinicStore } from '../store';
import { ActionConfirmModal } from '../_components/ActionConfirmModal';

export default function ActionCenterPage() {
  const items = useClinicStore((s) => s.actionCenterItems);
  const resolveItem = useClinicStore((s) => s.resolveActionCenterItem);

  const [filter, setFilter] = useState<'all' | 'pending' | 'resolved'>('pending');
  const [search] = useState('');
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<{
    id: string;
    title: string;
    description: string;
    confirmLabel: string;
    variant: 'emerald' | 'rose' | 'amber' | 'neutral';
  } | null>(null);

  const handleConfirmResolve = async () => {
    if (!pendingAction) return;
    setResolvingId(pendingAction.id);
    try {
      resolveItem(pendingAction.id);
    } finally {
      setResolvingId(null);
      setPendingAction(null);
    }
  };

  const filtered = items.filter((item) => {
    if (filter === 'pending' && item.status !== 'pending') return false;
    if (filter === 'resolved' && item.status !== 'resolved') return false;
    if (
      search &&
      !item.patient.toLowerCase().includes(search.toLowerCase()) &&
      !item.summary.toLowerCase().includes(search.toLowerCase())
    )
      return false;
    return true;
  });

  const pendingCount = items.filter((i) => i.status === 'pending').length;

  return (
    <div className="min-h-full flex flex-col gap-4 font-sans text-neutral-900 pb-24 lg:pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold tracking-tight text-neutral-950">
              Action Center
            </h1>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
              {pendingCount} Needs Doctor&apos;s Review
            </span>
          </div>
          <p className="text-xs text-neutral-500 mt-0.5 font-normal">
            Patient requests, prescription renewals, and urgent alerts flagged by Tulsi.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center p-0.5 rounded-lg bg-neutral-200/70">
            {(['pending', 'all', 'resolved'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setFilter(tab)}
                className={`px-3 py-1 rounded-md text-xs font-semibold capitalize transition-all cursor-pointer ${
                  filter === tab
                    ? 'bg-white text-neutral-900 shadow-2xs'
                    : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                {tab} {tab === 'pending' && `(${pendingCount})`}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 min-h-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {filtered.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center bg-white rounded-xl border border-neutral-200 p-6 text-center shadow-2xs">
            <CheckCircle2 className="w-10 h-10 text-emerald-600 mb-2" />
            <h3 className="text-sm font-bold text-neutral-900">No Pending Requests</h3>
            <p className="text-xs text-neutral-500 mt-1 max-w-sm">
              All callbacks, refill requests, and patient messages have been reviewed. You are completely caught up.
            </p>
          </div>
        ) : (
          filtered.map((item) => (
            <div
              key={item.id}
              className={`p-4 rounded-xl border transition-all ${
                item.status === 'resolved'
                  ? 'bg-neutral-50/60 border-neutral-200 opacity-60'
                  : item.urgency === 'critical'
                    ? 'bg-white border-rose-300 shadow-2xs'
                    : 'bg-white border-neutral-200 shadow-2xs'
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1.5 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${
                        item.urgency === 'critical'
                          ? 'bg-rose-50 text-rose-700 border-rose-200'
                          : item.urgency === 'high'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : 'bg-neutral-100 text-neutral-600 border-neutral-200'
                      }`}
                    >
                      {item.urgency === 'critical'
                        ? 'Urgent Patient Callback'
                        : item.type.toUpperCase()}
                    </span>
                    <h3 className="text-sm font-bold text-neutral-900">{item.summary}</h3>
                    <span className="text-xs text-neutral-400">· {item.time}</span>
                  </div>

                  <p className="text-xs font-semibold text-neutral-800">
                    Patient: {item.patient} ({item.age}, {item.gender}) ·{' '}
                    <span className="font-mono">{item.phone}</span>
                  </p>

                  <p className="text-xs text-neutral-600 leading-relaxed bg-neutral-50/80 border border-neutral-200/80 p-2.5 rounded-lg">
                    {item.notes}
                  </p>
                </div>

                <div className="flex sm:flex-col items-end gap-2 shrink-0">
                  {item.status === 'pending' ? (
                    <>
                      {item.type === 'callback' && (
                        <a
                          href={`tel:${item.phone}`}
                          className="px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-semibold flex items-center gap-1.5 shadow-2xs cursor-pointer"
                        >
                          <Phone className="w-3.5 h-3.5" />
                          <span>Call Patient</span>
                        </a>
                      )}
                      {item.type === 'refill' && (
                        <button
                          type="button"
                          disabled={resolvingId === item.id}
                          onClick={() =>
                            setPendingAction({
                              id: item.id,
                              title: 'Approve Prescription Renewal',
                              description: `Authorize 30-day medication refill for ${item.patient}? This will log your doctor signature and send an SMS pickup alert to ${item.phone}.`,
                              confirmLabel: 'Authorize Refill',
                              variant: 'emerald',
                            })
                          }
                          className="px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-semibold flex items-center gap-1.5 shadow-2xs cursor-pointer disabled:opacity-60"
                        >
                          {resolvingId === item.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5" />
                          )}
                          <span>Approve 30-day Refill</span>
                        </button>
                      )}
                      {item.type === 'lab' && (
                        <button
                          type="button"
                          disabled={resolvingId === item.id}
                          onClick={() =>
                            setPendingAction({
                              id: item.id,
                              title: 'Sign Off Diagnostics',
                              description: `Confirm doctor review of lab reports for ${item.patient}? This clears the flag and saves the report to the patient file.`,
                              confirmLabel: 'Sign Off & Archive',
                              variant: 'neutral',
                            })
                          }
                          className="px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-semibold flex items-center gap-1.5 shadow-2xs cursor-pointer disabled:opacity-60"
                        >
                          {resolvingId === item.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <FileCheck className="w-3.5 h-3.5" />
                          )}
                          <span>Sign Off &amp; Archive</span>
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={resolvingId === item.id}
                        onClick={() =>
                          setPendingAction({
                            id: item.id,
                            title: 'Mark as Resolved',
                            description: `Mark this inquiry for ${item.patient} as handled?`,
                            confirmLabel: 'Mark Handled',
                            variant: 'neutral',
                          })
                        }
                        className="text-xs text-neutral-500 hover:text-neutral-900 font-medium py-1 cursor-pointer disabled:opacity-60"
                      >
                        Mark Handled
                      </button>
                    </>
                  ) : (
                    <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Resolved
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <ActionConfirmModal
        isOpen={!!pendingAction}
        title={pendingAction?.title || ''}
        description={pendingAction?.description || ''}
        confirmLabel={pendingAction?.confirmLabel || 'Confirm'}
        variant={pendingAction?.variant || 'neutral'}
        isSubmitting={!!resolvingId}
        onConfirm={handleConfirmResolve}
        onClose={() => {
          if (!resolvingId) {
            setPendingAction(null);
          }
        }}
      />
    </div>
  );
}
