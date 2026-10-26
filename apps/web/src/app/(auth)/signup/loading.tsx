export default function SignupLoading() {
  return (
    <div className="animate-pulse space-y-4" aria-busy="true">
      <div className="h-6 w-36 rounded bg-[#DFD0B8]/50" />
      <div className="h-11 w-full rounded-xl border border-[#DFD0B8] bg-[#F8F5EF]" />
      <div className="h-11 w-full rounded-xl border border-[#DFD0B8] bg-[#F8F5EF]" />
      <div className="h-11 w-full rounded-xl border border-[#DFD0B8] bg-[#F8F5EF]" />
      <div className="h-11 w-full rounded-xl bg-[#0f0e0c]/90" />
    </div>
  );
}