'use client';

import React from 'react';
import { Bot, PhoneMissed, ShieldAlert, Search } from 'lucide-react';

type TabType = 'all' | 'missed' | 'ai' | 'emergency';

interface CallsFilterBarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  counts: {
    all: number;
    ai: number;
    emergency: number;
    missed: number;
  };
}

export function CallsFilterBar({
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  counts,
}: CallsFilterBarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div className="flex items-center gap-1.5 p-1 bg-neutral-100/90 rounded-2xl border border-neutral-200/70 text-xs font-medium overflow-x-auto [scrollbar-width:none]">
        <button
          type="button"
          onClick={() => onTabChange('all')}
          className={`px-3 py-1.5 rounded-xl transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
            activeTab === 'all'
              ? 'bg-white text-neutral-950 font-bold shadow-2xs'
              : 'text-neutral-600 hover:text-neutral-900 hover:bg-neutral-200/50'
          }`}
        >
          <span>All Calls</span>
          <span
            className={`px-1.5 rounded-md text-[10px] font-mono ${
              activeTab === 'all' ? 'bg-neutral-100 text-neutral-900' : 'text-neutral-400'
            }`}
          >
            {counts.all}
          </span>
        </button>

        <button
          type="button"
          onClick={() => onTabChange('ai')}
          className={`px-3 py-1.5 rounded-xl transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
            activeTab === 'ai'
              ? 'bg-emerald-600 text-white font-bold shadow-2xs'
              : 'text-emerald-700 hover:bg-emerald-50'
          }`}
        >
          <Bot className="w-3.5 h-3.5" />
          <span>Handled by Tulsi</span>
          <span
            className={`px-1.5 rounded-md text-[10px] font-mono ${
              activeTab === 'ai' ? 'bg-emerald-700 text-white' : 'text-emerald-600/80'
            }`}
          >
            {counts.ai}
          </span>
        </button>

        <button
          type="button"
          onClick={() => onTabChange('emergency')}
          className={`px-3 py-1.5 rounded-xl transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
            activeTab === 'emergency'
              ? 'bg-amber-600 text-white font-bold shadow-2xs'
              : 'text-amber-700 hover:bg-amber-50'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>Emergency</span>
          <span
            className={`px-1.5 rounded-md text-[10px] font-mono ${
              activeTab === 'emergency' ? 'bg-amber-700 text-white' : 'text-amber-600/80'
            }`}
          >
            {counts.emergency}
          </span>
        </button>

        <button
          type="button"
          onClick={() => onTabChange('missed')}
          className={`px-3 py-1.5 rounded-xl transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
            activeTab === 'missed'
              ? 'bg-rose-600 text-white font-bold shadow-2xs'
              : 'text-rose-600 hover:bg-rose-50'
          }`}
        >
          <PhoneMissed className="w-3.5 h-3.5" />
          <span>Missed</span>
          <span
            className={`px-1.5 rounded-md text-[10px] font-mono ${
              activeTab === 'missed' ? 'bg-rose-700 text-white' : 'text-rose-500'
            }`}
          >
            {counts.missed}
          </span>
        </button>
      </div>

      <div className="relative min-w-[240px] sm:w-72">
        <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          placeholder="Search phone, patient, notes..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-9 pr-3 py-1.5 bg-white border border-neutral-200/90 rounded-2xl text-xs text-neutral-900 placeholder:text-neutral-400 focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-400 transition-all shadow-2xs"
        />
      </div>
    </div>
  );
}
