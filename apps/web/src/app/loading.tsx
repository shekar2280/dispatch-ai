import React from 'react';
import { Loader2 } from 'lucide-react';

export default function GlobalLoading() {
  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center gap-3 bg-[#F1F4EE] text-sm text-[rgba(13,38,34,0.7)] font-sans">
      <Loader2 className="h-6 w-6 animate-spin text-[#1E6B56]" />
      <span className="font-semibold text-[#0D2622]">Loading...</span>
    </div>
  );
}
