'use client';

import React, { useState } from 'react';
import {
  Users,
  CalendarCheck,
  UserX,
  Clock,
  BarChart3,
  PieChart,
  Loader2,
  PhoneCall,
  UserPlus,
  Banknote,
  RefreshCw,
} from 'lucide-react';
import { useClinicStore } from '../store';
import { useClinicAnalyticsQuery, useClinicBillingCatalogQuery } from '../_hooks/useClinicQueries';
import { AnalyticsPageSkeleton } from '../_components/ClinicSkeletons';

export default function ClinicAnalyticsPage() {
  const orgId = useClinicStore((s) => s.orgId);
  const [selectedPeriod, setSelectedPeriod] = useState<'week' | 'month' | 'year'>('month');

  const {
    data: clinicAnalytics,
    isLoading: isAnalyticsLoading,
    isRefetching,
    refetch,
  } = useClinicAnalyticsQuery(orgId, selectedPeriod);
  const { data: billingCatalog } = useClinicBillingCatalogQuery(orgId);
  const currencySymbol = billingCatalog?.currency_symbol || '';

  const trends = clinicAnalytics?.daily_trends || [];
  const maxTotal = Math.max(...trends.map((t) => t.total), 1);
  const totalBookings = clinicAnalytics?.total_appointments ?? clinicAnalytics?.total_appointments_30d ?? 0;
  const completedCount = clinicAnalytics?.completed_count ?? clinicAnalytics?.completed_count_30d ?? 0;
  const completionRate = clinicAnalytics?.completion_rate_pct ?? (totalBookings > 0 ? Math.round((completedCount / totalBookings) * 100) : 0);
  const noShowRate = clinicAnalytics?.no_show_rate_pct ?? 0;
  const utilization = clinicAnalytics?.slot_utilization_pct ?? 0;
  const totalRevenue = clinicAnalytics?.total_revenue ?? 0;
  const upiRevenue = clinicAnalytics?.upi_revenue ?? 0;
  const cashRevenue = clinicAnalytics?.cash_revenue ?? 0;
  const sources = clinicAnalytics?.source_breakdown || { ai_voice: 0, walk_in: 0, manual: 0 };
  const totalSourceVisits = (sources.ai_voice + sources.walk_in + sources.manual) || 1;

  const periodLabel =
    selectedPeriod === 'week'
      ? 'Past 7 Days'
      : selectedPeriod === 'month'
      ? 'Past 30 Days'
      : 'Past 12 Months';

  return (
    <div className="min-h-full flex flex-col gap-5 font-sans text-neutral-900 pb-24 lg:pb-16">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-neutral-200/70 pb-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-neutral-950">
            Practice Growth &amp; Clinical Analytics
          </h1>
          <p className="text-xs text-neutral-500 mt-0.5 font-normal">
            Practice activity, completion metrics, slot utilization, and revenue performance.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-center">
          <div className="flex items-center p-0.5 rounded-lg bg-neutral-200/70">
            {(['week', 'month', 'year'] as const).map((period) => (
              <button
                key={period}
                type="button"
                onClick={() => setSelectedPeriod(period)}
                className={`px-3 py-1 rounded-md text-xs font-semibold capitalize transition-all whitespace-nowrap cursor-pointer ${
                  selectedPeriod === period
                    ? 'bg-white text-neutral-900 shadow-2xs'
                    : 'text-neutral-600 hover:text-neutral-900'
                }`}
              >
                {period === 'week' ? 'Week' : period === 'month' ? 'Month' : 'Year'}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="p-1.5 rounded-lg bg-white border border-neutral-200 text-neutral-600 hover:text-black hover:bg-neutral-50 transition-colors shadow-2xs disabled:opacity-50 cursor-pointer"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {isAnalyticsLoading && !clinicAnalytics ? (
        <AnalyticsPageSkeleton />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
            <div className="p-4 rounded-xl bg-white border border-neutral-200/90 shadow-2xs flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[10.5px] font-bold uppercase tracking-wider text-neutral-500">
                  Bookings ({selectedPeriod})
                </span>
                <CalendarCheck className="w-4 h-4 text-neutral-400" />
              </div>
              <p className="text-2xl font-black text-neutral-900 mt-2">{totalBookings}</p>
              <p className="text-[11px] text-neutral-500 mt-1">
                Completed: <strong className="text-neutral-800">{completedCount}</strong> ({completionRate}%)
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white border border-neutral-200/90 shadow-2xs flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[10.5px] font-bold uppercase tracking-wider text-neutral-500">
                  Revenue ({selectedPeriod})
                </span>
                <Banknote className="w-4 h-4 text-neutral-400" />
              </div>
              <p className="text-2xl font-bold text-neutral-900 mt-2">{currencySymbol}{totalRevenue}</p>
              <p className="text-[11px] text-neutral-500 mt-1">
                UPI: <strong className="text-neutral-800">{currencySymbol}{upiRevenue}</strong> • Cash: <strong className="text-neutral-800">{currencySymbol}{cashRevenue}</strong>
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white border border-neutral-200/90 shadow-2xs flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[10.5px] font-bold uppercase tracking-wider text-neutral-500">
                  OPD Slot Utilization
                </span>
                <Clock className="w-4 h-4 text-neutral-400" />
              </div>
              <p className="text-2xl font-black text-neutral-900 mt-2">{utilization}%</p>
              <p className="text-[11px] text-neutral-500 mt-1">
                Active schedule occupancy
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white border border-neutral-200/90 shadow-2xs flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-[10.5px] font-bold uppercase tracking-wider text-neutral-500">
                  No-Show Rate
                </span>
                <UserX className="w-4 h-4 text-neutral-400" />
              </div>
              <p className="text-2xl font-black text-neutral-900 mt-2">{noShowRate}%</p>
              <p className="text-[11px] text-neutral-500 mt-1">
                Expired or unattended slots
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
            <div className="lg:col-span-8 rounded-2xl border border-neutral-200/90 bg-white p-5 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between pb-3 border-b border-neutral-100">
                <div>
                  <h3 className="text-xs font-bold text-neutral-900 uppercase tracking-wider">
                    {periodLabel} Appointments &amp; Attendance Trend
                  </h3>
                  <p className="text-[11px] text-neutral-500">Appointment distribution across {selectedPeriod}</p>
                </div>
                <BarChart3 className="w-4 h-4 text-neutral-400" />
              </div>

              <div className="relative flex-1 min-h-[220px] flex flex-col justify-end pt-6 select-none">
                <div className="absolute inset-0 flex flex-col justify-between pointer-events-none pb-7">
                  <div className="border-b border-dashed border-neutral-100 w-full flex items-center justify-between text-[10px] text-neutral-400 font-mono">
                    <span>{maxTotal}</span>
                  </div>
                  <div className="border-b border-dashed border-neutral-100 w-full flex items-center justify-between text-[10px] text-neutral-400 font-mono">
                    <span>{Math.round(maxTotal / 2)}</span>
                  </div>
                  <div className="border-b border-neutral-200 w-full" />
                </div>

                <div className="relative z-10 flex items-end justify-between gap-1 sm:gap-1.5 h-44 pb-1">
                  {trends.map((item, idx) => {
                    const percentage = Math.round((item.total / maxTotal) * 100);
                    const shouldShowLabel =
                      selectedPeriod === 'week'
                        ? true
                        : selectedPeriod === 'year'
                        ? true
                        : idx === 0 ||
                          idx === Math.floor(trends.length / 4) ||
                          idx === Math.floor(trends.length / 2) ||
                          idx === Math.floor((trends.length * 3) / 4) ||
                          idx === trends.length - 1;

                    return (
                      <div
                        key={item.date || idx}
                        className="flex-1 flex flex-col items-center h-full justify-end group relative min-w-0"
                      >
                        <div className="absolute -top-7 hidden group-hover:flex items-center px-2 py-0.5 rounded-md bg-neutral-900 text-white text-[10px] font-mono whitespace-nowrap z-30 shadow-md">
                          <span>{item.day_label || item.date}: {item.total} total</span>
                        </div>

                        <div className="w-full flex justify-center items-end h-full">
                          <div
                            style={{ height: item.total > 0 ? `${percentage}%` : '2px' }}
                            className={`w-full max-w-[12px] sm:max-w-[16px] transition-all duration-150 ${
                              item.total > 0
                                ? 'bg-neutral-900 hover:bg-neutral-700 rounded-t-[2px]'
                                : 'bg-neutral-200'
                            }`}
                          />
                        </div>

                        <div className="h-5 flex items-center justify-center mt-1">
                          {shouldShowLabel ? (
                            <span className="text-[10px] font-medium text-neutral-500 whitespace-nowrap">
                              {item.day_label}
                            </span>
                          ) : (
                            <span className="w-1 h-1 rounded-full bg-neutral-200" />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="lg:col-span-4 rounded-2xl border border-neutral-200/90 bg-white p-5 shadow-xs flex flex-col justify-between">
              <div className="flex items-center justify-between pb-3 border-b border-neutral-100">
                <h3 className="text-xs font-bold text-neutral-900 uppercase tracking-wider">
                  Booking Sources
                </h3>
                <PieChart className="w-4 h-4 text-neutral-400" />
              </div>

              <div className="flex flex-col gap-4 py-4">
                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-neutral-800 flex items-center gap-1.5">
                      <PhoneCall className="w-3.5 h-3.5 text-neutral-600" />
                      AI Voice Receptionist
                    </span>
                    <span className="font-bold text-neutral-900">
                      {sources.ai_voice} ({Math.round((sources.ai_voice / totalSourceVisits) * 100)}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-neutral-100 overflow-hidden">
                    <div
                      style={{ width: `${Math.round((sources.ai_voice / totalSourceVisits) * 100)}%` }}
                      className="h-full bg-neutral-900 rounded-full"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-neutral-800 flex items-center gap-1.5">
                      <Users className="w-3.5 h-3.5 text-neutral-600" />
                      Walk-In Patients
                    </span>
                    <span className="font-bold text-neutral-900">
                      {sources.walk_in} ({Math.round((sources.walk_in / totalSourceVisits) * 100)}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-neutral-100 overflow-hidden">
                    <div
                      style={{ width: `${Math.round((sources.walk_in / totalSourceVisits) * 100)}%` }}
                      className="h-full bg-neutral-700 rounded-full"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-neutral-800 flex items-center gap-1.5">
                      <UserPlus className="w-3.5 h-3.5 text-neutral-600" />
                      Staff Manual Booking
                    </span>
                    <span className="font-bold text-neutral-900">
                      {sources.manual} ({Math.round((sources.manual / totalSourceVisits) * 100)}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-neutral-100 overflow-hidden">
                    <div
                      style={{ width: `${Math.round((sources.manual / totalSourceVisits) * 100)}%` }}
                      className="h-full bg-neutral-400 rounded-full"
                    />
                  </div>
                </div>
              </div>

              <p className="text-[11px] text-neutral-400 border-t border-neutral-100 pt-3">
                Live reports synced with your clinic appointment records.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
