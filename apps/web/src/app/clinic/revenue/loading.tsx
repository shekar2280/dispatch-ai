import { RevenuePageSkeleton } from '../_components/ClinicSkeletons';

export default function RevenueLoading() {
  return (
    <div className="w-full space-y-4 pb-24 lg:pb-12 text-[#0D2622] select-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-[#0D2622]">Revenue Desk</h1>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5 font-normal">
            Real-time fee collection, payments, and daily cash tracking
          </p>
        </div>
      </div>
      <RevenuePageSkeleton />
    </div>
  );
}
