import { AnalyticsPageSkeleton } from '../_components/ClinicSkeletons';

export default function AnalyticsLoading() {
  return (
    <div className="min-h-full flex flex-col gap-5 font-sans text-[#0D2622] pb-24 lg:pb-16 select-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[rgba(13,38,34,0.08)] pb-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-[#0D2622]">
            Practice Growth &amp; Clinical Analytics
          </h1>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5 font-normal">
            Practice activity, completion metrics, slot utilization, and revenue performance.
          </p>
        </div>
      </div>
      <AnalyticsPageSkeleton />
    </div>
  );
}
