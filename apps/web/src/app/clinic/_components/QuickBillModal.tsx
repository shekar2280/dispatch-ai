'use client';

import React, { useEffect, useRef, useState } from 'react';
import { X, Plus, Banknote, QrCode, Loader2, ReceiptText, Check } from 'lucide-react';
import { BillItem } from '../types';
import { useClinicStore } from '../store';
import { useClinicBillingCatalogQuery } from '../_hooks/useClinicQueries';

interface QuickBillModalProps {
  isOpen: boolean;
  onClose: () => void;
  patientName: string;
  patientPhone?: string;
  initialFee?: number;
  initialPaymentStatus?: 'paid' | 'pending';
  initialPaymentMethod?: string | null;
  initialBillItems?: BillItem[];
  initialAmountPaid?: number;
  paymentReceipts?: Array<{ id: string; amount: number; method: string; reference?: string | null; received_at: string; received_by_name?: string | null }>;
  onCollect: (payload: {
    paymentMethod?: 'UPI' | 'Cash';
    paymentStatus: 'paid' | 'pending';
    fee: number;
    billItems: BillItem[];
    amountReceived?: number;
    reference?: string;
    idempotencyKey?: string;
    adjustmentReason?: string;
  }) => Promise<void>;
  isSubmitting?: boolean;
}

export default function QuickBillModal({ isOpen, onClose, patientName, patientPhone, initialFee, initialBillItems = [], initialAmountPaid = 0, initialPaymentStatus, onCollect, isSubmitting = false }: QuickBillModalProps) {
  const orgId = useClinicStore(s => s.orgId);
  const { data: catalog } = useClinicBillingCatalogQuery(orgId);
  const [fee, setFee] = useState('');
  const [items, setItems] = useState<BillItem[]>([]);
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [category, setCategory] = useState<'medicine' | 'procedure' | 'other'>('medicine');
  const [saving, setSaving] = useState<'Cash' | 'UPI' | null>(null);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const submission = useRef<{ fingerprint: string; key: string } | undefined>(undefined);

  const prevOpenRef = useRef(false);

  useEffect(() => {
    const justOpened = isOpen && !prevOpenRef.current;
    prevOpenRef.current = isOpen;

    if (!justOpened) return;

    const consultation = initialBillItems.find(item => item.category === 'consultation');
    setFee(String(consultation?.amount ?? initialFee ?? catalog?.consultation_fee ?? ''));
    setItems(initialBillItems.filter(item => item.category !== 'consultation'));
    setName(''); setPrice(''); setAdding(false); setError(''); setSaving(null); submission.current = undefined;
  }, [catalog?.consultation_fee, initialBillItems, initialFee, isOpen]);

  const consultationFee = Number(fee);
  const total = consultationFee + items.reduce((sum, item) => sum + item.amount, 0);
  const paid = initialPaymentStatus === 'paid';
  const busy = isSubmitting || !!saving;
  const currency = catalog?.currency_symbol || '';
  const field = 'h-10 w-full rounded-lg border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] px-3 text-xs font-medium text-[#0D2622] outline-none focus:border-[#0D2622] disabled:bg-[#E3EBE0]/30';

  const addItem = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !price.trim() || !Number.isFinite(Number(price)) || Number(price) < 0) return;
    setItems(previous => [...previous, { name: name.trim(), amount: Number(price), unit_price: Number(price), quantity: 1, category }]);
    setName(''); setPrice('');
  };

  const collect = async (method: 'Cash' | 'UPI') => {
    if (busy || paid) return;
    if (!currency || !fee.trim() || !Number.isFinite(total) || consultationFee < 0 || total < initialAmountPaid) { setError('Check the consultation fee and charges.'); return; }
    setSaving(method); setError('');
    const billItems = [{ name: initialBillItems.find(item => item.category === 'consultation')?.name || 'Consultation', category: 'consultation', amount: consultationFee }, ...items];
    const amountReceived = Math.round((total - initialAmountPaid) * 100) / 100;
    const payload = { paymentMethod: amountReceived > 0 ? method : undefined, paymentStatus: 'paid' as const, fee: total, billItems, amountReceived: amountReceived > 0 ? amountReceived : undefined, adjustmentReason: initialBillItems.length ? 'Charges confirmed at reception' : undefined };
    const fingerprint = JSON.stringify(payload);
    const key = submission.current?.fingerprint === fingerprint ? submission.current.key : crypto.randomUUID();
    submission.current = { fingerprint, key };
    try { await onCollect({ ...payload, idempotencyKey: key }); onClose(); }
    catch (err: any) { const detail = err?.data?.detail ?? err?.response?.data?.detail; setError(typeof detail === 'string' ? detail : detail?.message || err?.message || 'Unable to save payment. Try again.'); }
    finally { setSaving(null); }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0D2622]/60 p-3 backdrop-blur-sm sm:p-6">
      <div role="dialog" aria-modal="true" aria-labelledby="bill-title" className="flex max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-[#FFFFFF] border border-[rgba(13,38,34,0.14)] shadow-2xl">
        <header className="flex items-center gap-3 border-b border-[rgba(13,38,34,0.1)] px-5 py-5 sm:px-6 bg-[#F1F4EE]/60">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#E3EBE0] border border-[rgba(13,38,34,0.12)]"><ReceiptText className="h-5 w-5 text-[#1E6B56]" /></div>
          <h2 id="bill-title" className="flex-1 text-base font-bold tracking-tight text-[#0D2622]">{paid ? 'Paid bill' : 'Create bill'}</h2>
          <button type="button" aria-label="Close bill" disabled={busy} onClick={onClose} className="rounded-lg p-2 text-[rgba(13,38,34,0.5)] hover:bg-[#E3EBE0] hover:text-[#0D2622] transition-colors"><X className="h-4 w-4" /></button>
        </header>
        <div className="min-h-0 overflow-y-auto sm:grid sm:grid-cols-[minmax(0,1fr)_220px]">
          <div className="px-5 py-5 sm:px-6">
            <div className="mb-5 flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E3EBE0] text-xs font-bold text-[#0D2622] border border-[rgba(13,38,34,0.12)]">{patientName.trim().slice(0, 1).toUpperCase()}</div>
              <div className="min-w-0"><div className="break-words text-xs font-bold text-[#0D2622]">{patientName}</div><div className="mt-1 text-[11px] text-[rgba(13,38,34,0.6)]">{patientPhone || 'Patient'}</div></div>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_44px_96px] gap-2 border-y border-[rgba(13,38,34,0.12)] bg-[#F1F4EE]/70 px-2 py-2 text-[10px] font-bold uppercase tracking-wider text-[rgba(13,38,34,0.5)]"><span>Item</span><span className="text-center">Qty</span><span className="text-right">Amount</span></div>
            <div className="grid grid-cols-[minmax(0,1fr)_44px_96px] items-center gap-2 border-b border-[rgba(13,38,34,0.08)] py-4 pl-2">
              <label htmlFor="bill-consultation" className="text-xs font-semibold text-[#0D2622]">Consultation fee</label><span className="text-center text-xs text-[rgba(13,38,34,0.5)]">1</span>
              <div className="flex items-center rounded-lg border border-[rgba(13,38,34,0.16)] px-2 text-xs bg-[#FFFFFF]"><span className="text-[rgba(13,38,34,0.5)]">{currency}</span><input id="bill-consultation" aria-label="Consultation fee" type="number" min="0" step="0.01" disabled={paid || busy} value={fee} onChange={e => setFee(e.target.value)} className="h-9 w-full min-w-0 bg-transparent text-right text-xs font-semibold text-[#0D2622] outline-none" /></div>
            </div>
            {!paid && !!catalog?.visit_charge_types.length && <div className="flex flex-wrap gap-1.5 py-2">{catalog.visit_charge_types.map(type => <button type="button" key={type.id} disabled={busy} onClick={() => setFee(String(type.fee))} className="rounded-lg border border-[rgba(13,38,34,0.14)] bg-[#FFFFFF] px-2 py-1.5 text-[11px] font-medium text-[rgba(13,38,34,0.7)] hover:border-[#0D2622] hover:text-[#0D2622] transition-colors">{type.name} · {currency}{type.fee}</button>)}</div>}
            {items.map((item, index) => <div key={index} className="grid grid-cols-[minmax(0,1fr)_44px_96px] items-center gap-2 border-b border-[rgba(13,38,34,0.08)] py-3 pl-2">
              <div className="min-w-0"><div className="break-words text-xs font-semibold text-[#0D2622]">{item.name}</div>{!paid && <button type="button" disabled={busy} aria-label={`Remove ${item.name}`} onClick={() => setItems(previous => previous.filter((_, i) => i !== index))} className="mt-1 text-[10px] text-[rgba(13,38,34,0.5)] hover:text-rose-600 font-medium">Remove</button>}</div>
              <input aria-label={`Quantity for ${item.name}`} type="number" min="1" step="1" disabled={paid || busy} value={item.quantity || 1} onChange={e => { const quantity = Math.max(1, Math.floor(Number(e.target.value) || 1)); setItems(previous => previous.map((line, i) => i === index ? { ...line, quantity, amount: (line.unit_price ?? line.amount / (line.quantity || 1)) * quantity } : line)); }} className="h-8 w-full rounded-md border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] text-center text-xs text-[#0D2622] font-semibold" />
              <span className="pr-2 text-right text-xs font-bold tabular-nums text-[#0D2622]">{currency}{item.amount.toFixed(2)}</span>
            </div>)}
            {!paid && <div className="mt-4">
              {!adding ? <button type="button" disabled={busy} onClick={() => setAdding(true)} className="flex items-center gap-2 py-2 text-xs font-bold text-[#1E6B56] hover:text-[#143530] transition-colors cursor-pointer"><Plus className="h-4 w-4" />Add medicine or charge</button> : <form onSubmit={addItem} className="space-y-3 rounded-xl border border-[rgba(13,38,34,0.14)] bg-[#F1F4EE]/40 p-3">
                <div className="flex items-center justify-between"><span className="text-[11px] font-bold text-[#0D2622]">New item</span><button type="button" aria-label="Close new item" onClick={() => { setAdding(false); setName(''); setPrice(''); }} className="p-1 text-[rgba(13,38,34,0.5)] hover:text-[#0D2622]"><X className="h-3.5 w-3.5" /></button></div>
                <input autoFocus aria-label="Item name" disabled={busy} placeholder="Medicine or charge name" value={name} onChange={e => setName(e.target.value)} className={field} />
                <div className="grid grid-cols-2 gap-2"><select aria-label="Item category" disabled={busy} value={category} onChange={e => setCategory(e.target.value as typeof category)} className={field}><option value="medicine">Medicine</option><option value="procedure">Procedure</option><option value="other">Other</option></select><input aria-label="Item price" disabled={busy} type="number" min="0" step="0.01" placeholder="Amount" value={price} onChange={e => setPrice(e.target.value)} className={field} /></div>
                <button type="submit" disabled={busy || !name.trim() || !price.trim()} className="flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-[#E3EBE0] text-xs font-bold text-[#0D2622] hover:bg-[#BFDDCD] disabled:opacity-40 cursor-pointer transition-colors"><Plus className="h-3.5 w-3.5" />Add item</button>
              </form>}
              {!!catalog?.billing_catalog.length && <div className="mt-3 flex flex-wrap gap-2">{catalog.billing_catalog.map(item => <button type="button" key={item.id} disabled={busy} onClick={() => setItems(previous => [...previous, { id: item.id, name: item.name, category: item.category, amount: item.unit_price, unit_price: item.unit_price, quantity: 1 }])} className="inline-flex items-center gap-1 rounded-lg border border-[rgba(13,38,34,0.14)] bg-[#FFFFFF] px-2 py-1.5 text-[11px] font-medium text-[rgba(13,38,34,0.7)] hover:border-[#0D2622] hover:text-[#0D2622]"><Plus className="h-3 w-3" />{item.name}</button>)}</div>}
            </div>}
          </div>
          <aside className="flex flex-col border-t border-[rgba(13,38,34,0.1)] bg-[#F1F4EE] p-5 sm:border-l sm:border-t-0">
            <div className="text-[11px] font-bold uppercase tracking-wider text-[rgba(13,38,34,0.5)]">Bill summary</div>
            <div className="mt-5 space-y-3 text-[11px] text-[rgba(13,38,34,0.7)]"><div className="flex justify-between gap-2 font-medium"><span>Consultation</span><span className="tabular-nums text-[#0D2622] font-semibold">{currency}{Number.isFinite(consultationFee) ? consultationFee.toFixed(2) : '0.00'}</span></div>{items.length > 0 && <div className="flex justify-between gap-2 font-medium"><span>Other charges</span><span className="tabular-nums text-[#0D2622] font-semibold">{currency}{items.reduce((sum, item) => sum + item.amount, 0).toFixed(2)}</span></div>}</div>
            <div className="mb-6 mt-5 border-t border-dashed border-[rgba(13,38,34,0.2)] pt-4"><div className="text-[11px] font-semibold text-[rgba(13,38,34,0.6)]">Total</div><div className="mt-1 text-2xl font-bold tracking-tight tabular-nums text-[#0D2622]">{currency}{Number.isFinite(total) ? total.toFixed(2) : '0.00'}</div></div>
            <div className="mt-auto space-y-2">
              {paid ? <><div className="mb-3 flex items-center gap-1.5 text-xs font-bold text-[#1E6B56]"><Check className="h-4 w-4" />Paid</div><button type="button" onClick={onClose} className="h-10 w-full rounded-xl bg-[#0D2622] text-xs font-bold text-[#F1F4EE] cursor-pointer">Done</button></> : <>
                <div className="mb-3 text-[11px] font-semibold text-[rgba(13,38,34,0.6)]">Confirm payment</div>
                <button type="button" disabled={busy || !currency || !fee.trim() || !!name.trim() || !!price.trim()} onClick={() => collect('UPI')} className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-[#0D2622] text-xs font-bold text-[#F1F4EE] hover:bg-[#143530] disabled:opacity-40 cursor-pointer shadow-xs transition-colors">{saving === 'UPI' ? <Loader2 className="h-4 w-4 animate-spin" /> : <QrCode className="h-4 w-4 text-[#F4B63A]" />}Paid by UPI</button>
                <button type="button" disabled={busy || !currency || !fee.trim() || !!name.trim() || !!price.trim()} onClick={() => collect('Cash')} className="flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-[rgba(13,38,34,0.18)] bg-[#FFFFFF] text-xs font-bold text-[#0D2622] hover:bg-[#E3EBE0] disabled:opacity-40 cursor-pointer transition-colors">{saving === 'Cash' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Banknote className="h-4 w-4 text-[#1E6B56]" />}Paid by cash</button>
              </>}
              {error && <div role="alert" className="rounded-lg bg-rose-50 border border-rose-200 p-2 text-xs text-rose-700">{error}</div>}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
