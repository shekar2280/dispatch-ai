import React from 'react';

export type CardVariant = 'default' | 'glass' | 'dark' | 'indigo' | 'rose' | 'emerald';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  hoverable?: boolean;
  children: React.ReactNode;
  className?: string;
}

const cardStyles: Record<CardVariant, string> = {
  default: 'bg-white border-slate-200 shadow-xs',
  glass: 'bg-white/80 backdrop-blur-xl border-slate-200/80 shadow-sm',
  dark: 'bg-slate-900 border-slate-800 text-white shadow-xl',
  indigo: 'bg-indigo-950/90 backdrop-blur-xl border-indigo-500/40 text-white shadow-indigo-950/50 shadow-xl',
  rose: 'bg-rose-950/90 backdrop-blur-xl border-rose-500/40 text-white shadow-rose-950/50 shadow-xl',
  emerald: 'bg-emerald-950/90 backdrop-blur-xl border-emerald-500/40 text-white shadow-emerald-950/50 shadow-xl',
};

export function Card({
  variant = 'default',
  hoverable = false,
  children,
  className = '',
  ...props
}: CardProps) {
  const base = 'rounded-2xl border p-5 transition-all';
  const style = cardStyles[variant] || cardStyles.default;
  const hover = hoverable ? 'hover:shadow-md hover:border-slate-300 active:scale-[0.99] cursor-pointer' : '';

  return (
    <div className={`${base} ${style} ${hover} ${className}`} {...props}>
      {children}
    </div>
  );
}
