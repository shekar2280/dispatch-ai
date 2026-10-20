import { CallsPageSkeleton } from '../_components/ClinicSkeletons';

export default function CallsLoading() {
  return (
    <div className="w-full space-y-4 font-sans text-[#0D2622] pb-20 select-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-[#0D2622]">
            Call Records &amp; AI Reception
          </h1>
          <p className="text-xs text-[rgba(13,38,34,0.65)] mt-0.5 font-normal">
            Review caller logs, AI reception transcripts, triage tags, and audio recordings.
          </p>
        </div>
      </div>
      <CallsPageSkeleton />
    </div>
  );
}
