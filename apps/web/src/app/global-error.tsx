'use client';

import React from 'react';

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#F1F4EE] text-[#0D2622] flex items-center justify-center p-6 font-sans">
        <div className="w-full max-w-md bg-[#FFFFFF] rounded-2xl border border-[rgba(13,38,34,0.16)] p-8 shadow-2xl text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-[#E3EBE0] text-[#0D2622] border border-[rgba(13,38,34,0.12)] flex items-center justify-center mx-auto font-bold text-lg">
            !
          </div>
          <h2 className="text-xl font-bold text-[#0D2622]">Application Error</h2>
          <p className="text-xs text-[rgba(13,38,34,0.7)] leading-relaxed">
            A critical error occurred while initializing the application.
          </p>
          <button
            type="button"
            onClick={reset}
            className="px-5 py-2.5 rounded-xl bg-[#0D2622] text-[#F1F4EE] text-xs font-semibold hover:bg-[#143530] transition-colors cursor-pointer"
          >
            Reload Application
          </button>
        </div>
      </body>
    </html>
  );
}
