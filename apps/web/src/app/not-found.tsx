import Link from 'next/link';
import { ArrowUpRight, MapPinOff } from 'lucide-react';

export default function NotFound() {
  return (
    <main className="relative isolate flex min-h-dvh items-center justify-center overflow-hidden bg-[#F1F4EE] px-6 py-12 text-[#0D2622]">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(#BFDDCD_1px,transparent_1px)] [background-size:24px_24px] opacity-35" />
      <section aria-labelledby="not-found-title" className="relative w-full max-w-xl rounded-3xl border border-[rgba(13,38,34,0.14)] bg-white/95 p-7 shadow-[0_24px_80px_-32px_rgba(13,38,34,0.18)] sm:p-12">
        <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(13,38,34,0.55)]">
          <span className="text-[#0D2622] font-bold">Dispatch AI</span>
          <span className="rounded-full border border-[rgba(13,38,34,0.16)] bg-[#E3EBE0] px-3 py-1.5 text-[#0D2622]">Page not found</span>
        </div>
        <div aria-hidden="true" className="relative my-10 flex h-36 items-center justify-center sm:my-12">
          <span className="absolute select-none text-[132px] font-semibold leading-none tracking-tighter text-[#E3EBE0] sm:text-[160px]">404</span>
          <div className="relative flex h-16 w-16 rotate-6 items-center justify-center rounded-2xl bg-[#0D2622] text-[#F1F4EE] shadow-xl">
            <MapPinOff className="h-8 w-8 text-[#BFDDCD]" strokeWidth={1.5} />
          </div>
        </div>
        <h1 id="not-found-title" className="max-w-sm text-3xl font-semibold leading-tight tracking-tight sm:text-4xl text-[#0D2622]">This page has<br />gone missing.</h1>
        <Link href="/clinic/schedule" className="mt-8 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#0D2622] px-5 text-sm font-semibold text-[#F1F4EE] transition hover:bg-[#143530] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#0D2622]">
          Back to schedule <ArrowUpRight className="h-4 w-4" />
        </Link>
      </section>
    </main>
  );
}
