'use client';

import React, { useEffect, useState } from 'react';
import { Loader2, Plus, Save, Trash2 } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { httpClient } from '@/lib/api/httpClient';
import { createClient } from '@/lib/supabase/client';
import { useClinicStore } from '../../store';
import { useClinicBillingCatalogQuery, clinicQueryKeys } from '../../_hooks/useClinicQueries';
import { ClinicBillingCatalogItem, VisitChargeType } from '../../types';

const newId = () => typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `item-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function BillingCatalogSection() {
  const orgId = useClinicStore((s) => s.orgId);
  const queryClient = useQueryClient();
  const { data, isLoading } = useClinicBillingCatalogQuery(orgId);
  const [visitTypes, setVisitTypes] = useState<VisitChargeType[]>([]);
  const [catalog, setCatalog] = useState<ClinicBillingCatalogItem[]>([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!data) return;
    setVisitTypes(data.visit_charge_types);
    setCatalog(data.billing_catalog);
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      try {
        await httpClient.patch(`/api/v1/org/${orgId}`, { visit_charge_types: visitTypes, billing_catalog: catalog }, { orgId });
      } catch {
        const supabase = createClient();
        const { data, error } = await supabase.from('organizations').select('booking_settings').eq('id', orgId).maybeSingle();
        if (error || !data) throw error || new Error('Could not load clinic settings');
        const settings: Record<string, any> = { ...(data.booking_settings as Record<string, any> || {}), visit_charge_types: visitTypes, billing_catalog: catalog };
        const standard = visitTypes.find((item) => item.id === 'standard') || visitTypes[0];
        if (standard) settings.consultation_fee = standard.fee;
        const { error: saveError } = await supabase.from('organizations').update({ booking_settings: settings }).eq('id', orgId);
        if (saveError) throw saveError;
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: clinicQueryKeys.billingCatalog(orgId) });
      setMessage('Price list saved. It is now available during check-in and checkout.');
      window.setTimeout(() => setMessage(''), 3500);
    },
    onError: () => setMessage('Could not save the price list. Please try again.'),
  });

  const updateVisitType = (id: string, update: Partial<VisitChargeType>) => setVisitTypes((rows) => rows.map((row) => row.id === id ? { ...row, ...update } : row));
  const updateCatalogItem = (id: string, update: Partial<ClinicBillingCatalogItem>) => setCatalog((rows) => rows.map((row) => row.id === id ? { ...row, ...update } : row));

  if (isLoading) return <div className="flex items-center gap-2 text-xs text-neutral-500"><Loader2 className="h-4 w-4 animate-spin" />Loading clinic prices…</div>;

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-5 space-y-4">
        <div>
          <h2 className="text-sm font-bold text-neutral-950">Visit charges</h2>
          <p className="mt-1 text-xs text-neutral-500">Set the common consultation reasons and fees. Staff can still adjust the amount for an individual visit.</p>
        </div>
        <div className="space-y-2">
          {visitTypes.map((row) => (
            <div key={row.id} className="grid grid-cols-[1fr_130px_36px] gap-2 items-center">
              <input aria-label="Visit charge name" value={row.name} onChange={(e) => updateVisitType(row.id, { name: e.target.value })} className="h-9 rounded-lg border border-neutral-200 px-3 text-xs" placeholder="e.g. Standard consultation" />
              <label className="flex h-9 items-center rounded-lg border border-neutral-200 px-2 text-xs"><span className="mr-1 text-neutral-400">{data?.currency_symbol || ''}</span><input aria-label="Visit charge amount" type="number" min="0" value={row.fee} onChange={(e) => updateVisitType(row.id, { fee: Number(e.target.value) })} className="w-full outline-none" /></label>
              <button type="button" onClick={() => setVisitTypes((rows) => rows.filter((x) => x.id !== row.id))} className="grid h-9 w-9 place-items-center rounded-lg text-neutral-400 hover:bg-rose-50 hover:text-rose-600" aria-label="Remove visit charge"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
          <button type="button" onClick={() => setVisitTypes((rows) => [...rows, { id: newId(), name: '', fee: 0, active: true }])} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-semibold text-neutral-700 hover:bg-neutral-100"><Plus className="h-3.5 w-3.5" />Add visit type</button>
        </div>
      </section>

      <section className="rounded-2xl border border-neutral-200 bg-white p-4 sm:p-5 space-y-4">
        <div>
          <h2 className="text-sm font-bold text-neutral-950">Medicines and other billable items</h2>
          <p className="mt-1 text-xs text-neutral-500">Add items once. During checkout staff can select an item, set its quantity, and the line total is calculated automatically.</p>
        </div>
        <div className="space-y-2">
          {catalog.map((row) => (
            <div key={row.id} className="grid grid-cols-[1fr_110px_125px_36px] gap-2 items-center">
              <input aria-label="Billable item name" value={row.name} onChange={(e) => updateCatalogItem(row.id, { name: e.target.value })} className="h-9 rounded-lg border border-neutral-200 px-3 text-xs" placeholder="Medicine or service name" />
              <label className="flex h-9 items-center rounded-lg border border-neutral-200 px-2 text-xs"><span className="mr-1 text-neutral-400">{data?.currency_symbol || ''}</span><input aria-label="Unit price" type="number" min="0" value={row.unit_price} onChange={(e) => updateCatalogItem(row.id, { unit_price: Number(e.target.value) })} className="w-full outline-none" /></label>
              <select aria-label="Item category" value={row.category} onChange={(e) => updateCatalogItem(row.id, { category: e.target.value })} className="h-9 rounded-lg border border-neutral-200 bg-white px-2 text-xs"><option value="medicine">Medicine</option><option value="procedure">Procedure</option><option value="other">Other</option></select>
              <button type="button" onClick={() => setCatalog((rows) => rows.filter((x) => x.id !== row.id))} className="grid h-9 w-9 place-items-center rounded-lg text-neutral-400 hover:bg-rose-50 hover:text-rose-600" aria-label="Remove billable item"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
          <button type="button" onClick={() => setCatalog((rows) => [...rows, { id: newId(), name: '', unit_price: 0, category: 'medicine', active: true }])} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-semibold text-neutral-700 hover:bg-neutral-100"><Plus className="h-3.5 w-3.5" />Add catalog item</button>
        </div>
      </section>

      <div className="flex items-center justify-between gap-3">
        <p role="status" className="text-xs text-neutral-500">{message}</p>
        <button type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="inline-flex items-center gap-2 rounded-xl bg-neutral-950 px-4 py-2.5 text-xs font-semibold text-white hover:bg-neutral-800 disabled:opacity-60">
          {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{saveMutation.isPending ? 'Saving…' : 'Save price list'}
        </button>
      </div>
    </div>
  );
}
