import React from 'react';
import { StatusDot, StatusDotVariant } from './StatusDot';

export type BadgeVariant = 'emerald' | 'rose' | 'amber' | 'indigo' | 'purple' | 'slate' | 'sky' | 'teal';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  dot?: boolean;
  dotPing?: boolean;
  className?: string;
  icon?: React.ReactNode;
}

const badgeStyles: Record<BadgeVariant, string> = {
  emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
  rose: 'bg-rose-50 text-rose-700 border-rose-200/80',
  amber: 'bg-amber-50 text-amber-800 border-amber-200/80',
  indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200/80',
  purple: 'bg-purple-50 text-purple-700 border-purple-200/80',
  slate: 'bg-slate-100 text-slate-700 border-slate-200',
  sky: 'bg-sky-50 text-sky-700 border-sky-200/80',
  teal: 'bg-teal-50 text-teal-700 border-teal-200/80',
};

const dotVariantMap: Record<BadgeVariant, StatusDotVariant> = {
  emerald: 'emerald',
  rose: 'rose',
  amber: 'amber',
  indigo: 'indigo',
  purple: 'indigo',
  slate: 'slate',
  sky: 'sky',
  teal: 'emerald',
};

export function Badge({
  variant = 'slate',
  children,
  dot = false,
  dotPing = false,
  className = '',
  icon,
}: BadgeProps) {
  const style = badgeStyles[variant] || badgeStyles.slate;
  const dotColor = dotVariantMap[variant] || 'slate';

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold border transition-colors ${style} ${className}`}
    >
      {dot && <StatusDot variant={dotColor} ping={dotPing} size="sm" />}
      {icon && <span className="flex items-center">{icon}</span>}
      <span>{children}</span>
    </span>
  );
}
