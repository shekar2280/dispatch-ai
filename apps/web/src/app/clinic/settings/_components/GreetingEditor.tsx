'use client';

import React from 'react';
import { RotateCcw, Check } from 'lucide-react';
import { GREETING_LANGUAGES } from '../../constants';

interface GreetingEditorProps {
  greetingPrompt: string;
  setGreetingPrompt: (value: string) => void;
  clinicName: string;
}

export function GreetingEditor({ greetingPrompt, setGreetingPrompt, clinicName }: GreetingEditorProps) {
  const name = clinicName.trim() || 'our clinic';
  const language = GREETING_LANGUAGES.find((item) => item.id === 'en') || GREETING_LANGUAGES[0];
  const personalize = (text: string) => text.replace(/\{\{?clinic_name\}?\}/gi, name);
  const templates = [
    { label: 'Standard', text: personalize(language.template) },
    { label: 'Warm', text: personalize(language.friendlyTemplate || language.template) },
    { label: 'Brief', text: personalize(language.conciseTemplate || language.template) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Greeting templates">
          <span className="mr-1 text-xs text-neutral-400">Start with</span>
          {templates.map((template) => {
            const selected = greetingPrompt.trim() === template.text;
            return <button key={template.label} type="button" aria-pressed={selected} onClick={() => setGreetingPrompt(template.text)} className={`inline-flex min-h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E6B56] ${selected ? 'border-[#BFDDCD] bg-[#E3EBE0]/70 text-[#1E6B56]' : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300 hover:bg-neutral-50'}`}>{selected && <Check className="h-3 w-3" />}{template.label}</button>;
          })}
        </div>
        <button type="button" onClick={() => setGreetingPrompt(templates[0].text)} title="Restore the standard greeting" className="inline-flex min-h-8 items-center gap-1.5 rounded-md px-1 text-xs text-neutral-400 transition hover:text-neutral-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E6B56]"><RotateCcw className="h-3 w-3" />Reset</button>
      </div>
      <div className="overflow-hidden rounded-xl border border-neutral-200 bg-[#FAFBF9] transition focus-within:border-[#1E6B56]/60 focus-within:ring-2 focus-within:ring-[#1E6B56]/10">
        <label htmlFor="reception-opening-greeting" className="sr-only">Opening greeting</label>
        <textarea id="reception-opening-greeting" rows={5} maxLength={500} value={greetingPrompt} onChange={(event) => setGreetingPrompt(event.target.value)} placeholder={`Hello! Welcome to ${name}. How can I help you today?`} className="block min-h-[170px] w-full resize-y border-0 bg-transparent px-4 py-4 text-sm leading-7 text-neutral-800 outline-none placeholder:text-neutral-400 focus:ring-0" aria-describedby="greeting-editor-hint" />
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-200/60 px-4 py-2.5 text-[11px] text-neutral-400"><span id="greeting-editor-hint">Make it sound like {name}.</span><span className="tabular-nums">{greetingPrompt.length} / 500</span></div>
      </div>
    </div>
  );
}
