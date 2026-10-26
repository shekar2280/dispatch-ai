'use client';

import { Suspense, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CalendarClock,
  CalendarDays,
  Clock3,
  Plus,
  Search,
  Pencil,
  Trash2,
  CheckCircle2,
  X,
  ChevronLeft,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from 'lucide-react';
import { useScheduleHistory } from '../../_hooks/useScheduleHistory';
import { useClinicTimezone } from '../../_hooks/useClinicQueries';
import { useClinicStore } from '../../store';
import { httpClient } from '@/lib/api/httpClient';
import {
  ScheduleChangeForm,
  ScheduleChange,
  ChangeKind,
  buttonClass,
  dateLabel,
  timeLabel,
} from '../_components/ScheduleChangeForm';

const PAGE_SIZE = 12;

export default function ScheduleChangesPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-neutral-500">Loading schedule changes…</p>}>
      <ScheduleChanges />
    </Suspense>
  );
}

function ScheduleChanges() {
  const router = useRouter();
  const params = useSearchParams();
  const orgId = useClinicStore((s) => s.orgId);
  const timezone = useClinicTimezone(orgId);
  const today = timezone
    ? new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date())
    : '';

  const queryClient = useQueryClient();
  const { items, isLoading, isError, refetch } = useScheduleHistory();
  const [editing, setEditing] = useState<ScheduleChange | undefined>();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sortAsc, setSortAsc] = useState(false);

  const type = params.get('type') || 'all';
  const period = params.get('view') || 'upcoming';
  const action = params.get('action');
  const kind: ChangeKind | null =
    editing?.type ||
    (action === 'leave' || action === 'special_hours' || action === 'emergency_closure'
      ? action
      : null);
  const requestedDate = params.get('date') || '';
  const initialDate =
    /^\d{4}-\d{2}-\d{2}$/.test(requestedDate) &&
      requestedDate >= today &&
      !Number.isNaN(Date.parse(requestedDate))
      ? requestedDate
      : today;

  function navigate(values: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    Object.entries(values).forEach(([key, value]) =>
      value ? next.set(key, value) : next.delete(key),
    );
    router.replace(`/clinic/schedule/history?${next}`, { scroll: false });
    setPage(1);
    setDeleting(null);
    setError('');
  }

  function closeForm() {
    setEditing(undefined);
    navigate({ action: null });
  }

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ['clinic-closures', orgId] });
    void queryClient.invalidateQueries({ queryKey: ['clinic'] });
    if (orgId && typeof BroadcastChannel !== 'undefined') {
      const channel = new BroadcastChannel('dispatch_clinic_sync');
      channel.postMessage({ type: 'SYNC', orgId, timestamp: Date.now() });
      channel.close();
    }
  }

  const filtered = useMemo(() => {
    return items
      .filter((i) => {
        if (type === 'leave' && i.type === 'special_hours') return false;
        if (type === 'special_hours' && i.type !== 'special_hours') return false;
        if (type === 'emergency_closure' && i.type !== 'emergency_closure') return false;
        if (period === 'upcoming' && i.endDate < today) return false;
        if (period === 'past' && i.endDate >= today) return false;
        const query = search.trim().toLowerCase();
        if (!query) return true;
        const haystack = `${i.title} ${i.reason || ''} ${i.startDate} ${i.endDate} ${i.customHours?.map((h) => `${h.start} ${h.end}`).join(' ') || ''
          }`.toLowerCase();
        return haystack.includes(query);
      })
      .sort((a, b) =>
        sortAsc ? a.startDate.localeCompare(b.startDate) : b.startDate.localeCompare(a.startDate),
      );
  }, [items, type, period, today, search, sortAsc]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);

  async function remove(item: ScheduleChange) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      if (item.isApi) {
        if (!orgId) throw new Error('Connect your clinic to remove this change.');
        await httpClient.delete(`/api/v1/org/${orgId}/closures/${item.id}`, { orgId });
      } else if (item.type === 'leave') {
        useClinicStore.getState().removeLeave(item.id);
      } else {
        useClinicStore.getState().removeDateOverride(item.id);
      }
      refresh();
      setDeleting(null);
      setMessage(`Removed “${item.title}”. Regular schedule now applies to these dates.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove this change. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full space-y-4 pb-16 pt-1 font-sans text-xs text-neutral-900">
      <Link
        href="/clinic/schedule"
        className="inline-flex items-center gap-2 text-xs font-medium text-neutral-500 hover:text-neutral-900 transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to schedule
      </Link>

      <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Schedule changes</h1>
          <p className="mt-0.5 max-w-xl text-xs leading-5 text-neutral-500">
            Vacations, doctor leaves, extended hours, and a clear record of past changes.
          </p>
        </div>
        {!kind && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              className={buttonClass}
              onClick={() => navigate({ action: 'special_hours' })}
            >
              <Clock3 className="h-4 w-4" />
              Extended Hours
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-800 transition-colors shadow-2xs"
              onClick={() => navigate({ action: 'leave' })}
            >
              <Plus className="h-4 w-4" />
              Vacation / Leave
            </button>
          </div>
        )}
      </header>

      {message && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"
        >
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{message}</span>
          <button aria-label="Dismiss confirmation" onClick={() => setMessage('')}>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {kind ? (
        today && (
          <ScheduleChangeForm
            key={editing?.id || kind}
            kind={kind}
            item={editing}
            initialDate={initialDate}
            today={today}
            timezone={timezone}
            orgId={orgId}
            onCancel={closeForm}
            onSaved={(msg) => {
              refresh();
              setMessage(msg);
              setEditing(undefined);
              navigate({ action: null, type: 'all', view: 'upcoming' });
              setSearch('');
            }}
          />
        )
      ) : (
        <section className="overflow-hidden rounded-2xl border border-neutral-200/90 bg-white shadow-xs">
          <div className="flex flex-col gap-3 border-b border-neutral-100 bg-neutral-50/50 p-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-400" />
              <input
                aria-label="Search schedule changes"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Search description or date..."
                className="w-full rounded-lg border border-neutral-200 bg-white py-1.5 pl-8 pr-7 text-xs outline-emerald-700 placeholder:text-neutral-400"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div
                className="inline-flex rounded-lg border border-neutral-200 bg-white p-0.5"
                role="group"
                aria-label="Status period"
              >
                {[
                  ['upcoming', 'Upcoming'],
                  ['past', 'Past'],
                  ['all', 'All'],
                ].map(([val, label]) => (
                  <button
                    key={val}
                    onClick={() => navigate({ view: val })}
                    className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${period === val
                        ? 'bg-neutral-900 text-white shadow-2xs'
                        : 'text-neutral-600 hover:text-neutral-900'
                      }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div
                className="inline-flex rounded-lg border border-neutral-200 bg-white p-0.5"
                role="group"
                aria-label="Change type"
              >
                {[
                  ['all', 'All'],
                  ['leave', 'Leaves'],
                  ['special_hours', 'Extended Hours'],
                ].map(([val, label]) => (
                  <button
                    key={val}
                    onClick={() => navigate({ type: val })}
                    className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${type === val
                        ? 'bg-neutral-900 text-white shadow-2xs'
                        : 'text-neutral-600 hover:text-neutral-900'
                      }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => setSortAsc(!sortAsc)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-neutral-700 hover:bg-neutral-50 transition-colors"
                title={sortAsc ? 'Sorting oldest to newest' : 'Sorting newest to oldest'}
              >
                {sortAsc ? (
                  <ArrowUp className="h-3.5 w-3.5 text-neutral-500" />
                ) : (
                  <ArrowDown className="h-3.5 w-3.5 text-neutral-500" />
                )}
                <span>{sortAsc ? 'Oldest first' : 'Newest first'}</span>
              </button>
            </div>
          </div>

          <div className="hidden border-b border-neutral-100 bg-neutral-50/80 px-4 py-2 text-[11px] font-semibold tracking-wider text-neutral-400 uppercase sm:grid sm:grid-cols-[minmax(0,1.2fr)_minmax(200px,0.8fr)_auto]">
            <span>Schedule event & description</span>
            <span>Dates & opening hours</span>
            <span className="text-right">Actions</span>
          </div>

          {isLoading || !today ? (
            <p role="status" className="p-8 text-center text-xs text-neutral-500">
              Loading schedule changes…
            </p>
          ) : isError ? (
            <div role="alert" className="p-8 text-center text-xs text-rose-700">
              Could not load schedule changes.
              <button className="ml-2 underline" onClick={() => void refetch()}>
                Try again
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <CalendarClock className="mx-auto mb-3 h-7 w-7 text-neutral-300" />
              <h2 className="font-semibold text-neutral-900">
                {search
                  ? 'No matching changes'
                  : period === 'past'
                    ? 'No past changes recorded'
                    : 'Your regular schedule is in place'}
              </h2>
              <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-neutral-500">
                {search
                  ? 'Try searching with another keyword or date.'
                  : 'Upcoming vacations, leaves, and extended hours will appear here.'}
              </p>
              {!search && (
                <button
                  className="mt-3.5 text-xs font-semibold text-emerald-800 hover:text-emerald-950 transition-colors"
                  onClick={() => navigate({ action: 'leave' })}
                >
                  Schedule leave or vacation →
                </button>
              )}
            </div>
          ) : (
            <div className="divide-y divide-neutral-100">
              {filtered
                .slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE)
                .map((item) => {
                  const special = item.type === 'special_hours';
                  const past = item.endDate < today;
                  const active = item.startDate <= today && !past;

                  return (
                    <article
                      key={item.id}
                      className="px-4 py-3 hover:bg-neutral-50/60 transition-colors"
                    >
                      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(200px,0.8fr)_auto] sm:items-center">
                        <div className="flex gap-3">
                          <div
                            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${special
                                ? 'bg-emerald-50 text-emerald-800'
                                : 'bg-amber-50 text-amber-700'
                              }`}
                          >
                            {special ? (
                              <Clock3 className="h-4 w-4" />
                            ) : (
                              <CalendarDays className="h-4 w-4" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="mb-0.5 flex flex-wrap items-center gap-2">
                              <span className="text-[11px] font-semibold text-neutral-700">
                                {special
                                  ? 'Extended Hours'
                                  : item.type === 'leave'
                                    ? 'Vacation / Leave'
                                    : 'Clinic Closure'}
                              </span>
                              <span
                                className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${past
                                    ? 'bg-neutral-100 text-neutral-500'
                                    : active
                                      ? 'bg-emerald-100 text-emerald-900'
                                      : 'bg-blue-50 text-blue-800'
                                  }`}
                              >
                                {past ? 'Completed' : active ? 'In effect today' : 'Upcoming'}
                              </span>
                            </div>
                            <h2 className="break-words text-xs font-semibold text-neutral-900">
                              {item.title}
                            </h2>
                            {item.reason && item.reason !== item.title && (
                              <p className="mt-0.5 break-words text-[11px] text-neutral-500">
                                {item.reason}
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="border-l border-neutral-100 pl-3 sm:border-l-0 sm:pl-0">
                          <p className="text-xs font-semibold text-neutral-800">
                            {dateLabel(item.startDate)}
                            {item.endDate !== item.startDate && (
                              <>
                                <span className="mx-1 text-neutral-400">–</span>
                                {dateLabel(item.endDate)}
                              </>
                            )}
                          </p>
                          {special && item.customHours?.length ? (
                            <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-neutral-600">
                              {item.customHours.map((h, i) => (
                                <span key={i} className="tabular-nums font-medium">
                                  {timeLabel(h.start)} – {timeLabel(h.end)}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-0.5 text-[11px] text-neutral-500 font-medium">
                              Closed all day
                            </p>
                          )}
                          {item.emergencyPhone && (
                            <p className="mt-0.5 text-[10px] text-neutral-400">
                              Urgent line: {item.emergencyPhone}
                            </p>
                          )}
                        </div>

                        <div className="flex items-center gap-1 sm:justify-end">
                          {!past && (
                            <>
                              {item.isApi && (
                                <button
                                  disabled={busy}
                                  className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-900 transition-colors"
                                  aria-label={`Edit ${item.title}`}
                                  onClick={() => {
                                    setEditing(item);
                                    setMessage('');
                                    setDeleting(null);
                                  }}
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </button>
                              )}
                              <button
                                disabled={busy}
                                className="rounded-lg p-1.5 text-neutral-400 hover:bg-rose-50 hover:text-rose-700 transition-colors"
                                aria-label={`Remove ${item.title}`}
                                onClick={() => {
                                  setDeleting(item.id);
                                  setError('');
                                }}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </>
                          )}
                        </div>
                      </div>

                      {deleting === item.id && (
                        <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50/70 p-3 text-rose-900">
                          <h3 className="text-xs font-semibold">Remove this schedule change?</h3>
                          <p className="mt-1 text-xs leading-5 text-rose-800">
                            “{item.title}” will be removed. Regular clinic hours will resume for
                            these dates.
                          </p>
                          {error && (
                            <p role="alert" className="mt-2 text-xs font-medium text-rose-900">
                              {error}
                            </p>
                          )}
                          <div className="mt-3 flex gap-2">
                            <button
                              disabled={busy}
                              onClick={() => setDeleting(null)}
                              className={buttonClass}
                            >
                              Keep change
                            </button>
                            <button
                              disabled={busy}
                              onClick={() => void remove(item)}
                              className="rounded-xl bg-rose-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-800 disabled:opacity-50 transition-colors shadow-2xs"
                            >
                              {busy ? 'Removing…' : 'Remove change'}
                            </button>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
            </div>
          )}

          {filtered.length > 0 && (
            <footer className="flex items-center justify-between border-t border-neutral-100 bg-neutral-50/40 px-4 py-2.5 text-[11px] text-neutral-500">
              <span>
                {(current - 1) * PAGE_SIZE + 1}–{Math.min(current * PAGE_SIZE, filtered.length)} of{' '}
                {filtered.length} changes
              </span>
              <div className="flex items-center gap-3">
                <button
                  aria-label="Previous page"
                  disabled={current === 1}
                  onClick={() => setPage(current - 1)}
                  className="rounded-lg border border-neutral-200 bg-white p-1.5 hover:bg-neutral-50 disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <span className="font-medium text-neutral-700">
                  {current} / {pages}
                </span>
                <button
                  aria-label="Next page"
                  disabled={current === pages}
                  onClick={() => setPage(current + 1)}
                  className="rounded-lg border border-neutral-200 bg-white p-1.5 hover:bg-neutral-50 disabled:opacity-30 transition-colors"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </footer>
          )}
        </section>
      )}
    </div>
  );
}
