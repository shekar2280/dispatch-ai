'use client';

import React from 'react';
import {
  X,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';

interface ActionConfirmModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: 'emerald' | 'rose' | 'amber' | 'neutral';
  isSubmitting?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ActionConfirmModal({
  isOpen,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  variant = 'neutral',
  isSubmitting = false,
  onConfirm,
  onClose,
}: ActionConfirmModalProps) {
  if (!isOpen) return null;

  const variantStyles = {
    emerald: {
      icon: <CheckCircle2 className="w-5 h-5 text-[#1E6B56]" />,
      iconBg: 'bg-[#BFDDCD]/30 border-[#1E6B56]/30',
      confirmBtn: 'bg-[#1E6B56] hover:bg-[#143530] text-[#F1F4EE]',
    },
    rose: {
      icon: <AlertCircle className="w-5 h-5 text-rose-600" />,
      iconBg: 'bg-rose-50 border-rose-200',
      confirmBtn: 'bg-rose-600 hover:bg-rose-700 text-white shadow-rose-600/20',
    },
    amber: {
      icon: <AlertTriangle className="w-5 h-5 text-[#F4B63A]" />,
      iconBg: 'bg-[#F4B63A]/10 border-[#F4B63A]/30',
      confirmBtn: 'bg-[#F4B63A] hover:bg-[#ffc75c] text-[#0D2622]',
    },
    neutral: {
      icon: <CheckCircle2 className="w-5 h-5 text-[#0D2622]" />,
      iconBg: 'bg-[#E3EBE0] border-[rgba(13,38,34,0.15)]',
      confirmBtn: 'bg-[#0D2622] hover:bg-[#143530] text-[#F1F4EE]',
    },
  }[variant];

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-[#0D2622]/60 backdrop-blur-sm transition-all animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div className="w-full max-w-md bg-[#FFFFFF] rounded-2xl border border-[rgba(13,38,34,0.16)] shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-150">
        <div className="px-5 py-4 border-b border-[rgba(13,38,34,0.08)] flex items-center justify-between bg-[#F1F4EE]">
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${variantStyles.iconBg}`}>
              {variantStyles.icon}
            </div>
            <h3 className="text-sm font-bold text-[#0D2622] leading-tight">
              {title}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="w-7 h-7 rounded-lg border border-[rgba(13,38,34,0.14)] hover:bg-[#E3EBE0] flex items-center justify-center text-[rgba(13,38,34,0.5)] hover:text-[#0D2622] transition-colors cursor-pointer disabled:opacity-50"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="p-5">
          <p className="text-xs text-[rgba(13,38,34,0.75)] leading-relaxed">
            {description}
          </p>
        </div>

        <div className="px-5 py-3.5 border-t border-[rgba(13,38,34,0.08)] bg-[#F1F4EE]/60 flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-3.5 py-1.5 rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#FFFFFF] hover:bg-[#E3EBE0] text-[#0D2622] text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isSubmitting}
            className={`px-4 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed ${variantStyles.confirmBtn}`}
          >
            {isSubmitting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : null}
            <span>{isSubmitting ? 'Processing...' : confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
