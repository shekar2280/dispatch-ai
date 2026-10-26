import React from 'react';

export type StatusDotVariant = 'emerald' | 'rose' | 'amber' | 'indigo' | 'sky' | 'slate';

interface StatusDotProps {
  variant?: StatusDotVariant;
  ping?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const colorMap: Record<StatusDotVariant, { ping: string; dot: string }> = {
  emerald: { ping: 'bg-emerald-400', dot: 'bg-emerald-500' },
  rose: { ping: 'bg-rose-400', dot: 'bg-rose-500' },
  amber: { ping: 'bg-amber-400', dot: 'bg-amber-500' },
  indigo: { ping: 'bg-indigo-400', dot: 'bg-indigo-500' },
  sky: { ping: 'bg-sky-400', dot: 'bg-sky-500' },
  slate: { ping: 'bg-slate-400', dot: 'bg-slate-500' },
};

const sizeMap = {
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
  lg: 'h-3 w-3',
};

export function StatusDot({
  variant = 'emerald',
  ping = true,
  size = 'md',
  className = '',
}: StatusDotProps) {
  const colors = colorMap[variant] || colorMap.emerald;
  const sizeClasses = sizeMap[size] || sizeMap.md;

  return (
    <span className={`relative flex ${sizeClasses} ${className}`}>
      {ping && (
        <span
          className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${colors.ping}`}
        />
      )}
      <span className={`relative inline-flex rounded-full ${sizeClasses} ${colors.dot}`} />
    </span>
  );
}
