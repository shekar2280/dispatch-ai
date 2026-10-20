'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { AlertCircle, RotateCcw, Home } from 'lucide-react';

export default function ClinicError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-full flex-1 flex flex-col items-center justify-center p-6 bg-[#F1F4EE] text-[#0D2622] font-sans">
      <div className="w-full max-w-md bg-[#FFFFFF] rounded-2xl border border-[rgba(13,38,34,0.14)] p-8 shadow-xl text-center space-y-5">
        <div className="w-14 h-14 rounded-2xl bg-[#E3EBE0] text-[#1E6B56] border border-[rgba(13,38,34,0.12)] flex items-center justify-center mx-auto shadow-sm">
          <AlertCircle className="w-7 h-7" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-bold tracking-tight text-[#0D2622]">
            Workspace Error
          </h2>
          <p className="text-xs text-[rgba(13,38,34,0.65)] leading-relaxed">
            An unexpected error occurred while loading this clinic workspace module.
          </p>
        </div>

        {error.message && (
          <div className="p-3 rounded-xl bg-[#F1F4EE] border border-[rgba(13,38,34,0.1)] text-left text-xs font-mono text-[rgba(13,38,34,0.8)] break-all max-h-24 overflow-y-auto">
            {error.message}
          </div>
        )}

        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0D2622] hover:bg-[#143530] text-[#F1F4EE] text-xs font-semibold shadow-xs transition-colors cursor-pointer"
          >
            <RotateCcw className="w-4 h-4 text-[#F4B63A]" />
            <span>Try again</span>
          </button>
          <Link
            href="/clinic"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] hover:bg-[#E3EBE0] text-[#0D2622] text-xs font-semibold transition-colors"
          >
            <Home className="w-4 h-4" />
            <span>Chamber</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
