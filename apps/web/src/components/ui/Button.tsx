import React from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'emerald' | 'amber' | 'rose' | 'outline' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-slate-900 hover:bg-slate-800 text-white shadow-xs',
  secondary: 'bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200',
  emerald: 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-950/30 shadow-md',
  amber: 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-black shadow-amber-950/40 shadow-lg',
  rose: 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-950/30 shadow-md',
  outline: 'bg-transparent hover:bg-slate-50 text-slate-700 border border-slate-200 shadow-xs',
  ghost: 'bg-transparent hover:bg-slate-100 text-slate-700 border-transparent',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'py-1.5 px-3 text-xs rounded-lg gap-1.5',
  md: 'py-2.5 px-4 text-xs font-bold rounded-xl gap-2',
  lg: 'py-3 px-5 text-sm font-bold rounded-xl gap-2.5',
};

export function Button({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  icon,
  children,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  const variantClass = variantStyles[variant] || variantStyles.primary;
  const sizeClass = sizeStyles[size] || sizeStyles.md;

  return (
    <button
      disabled={disabled || isLoading}
      className={`inline-flex items-center justify-center font-sans transition-all active:scale-98 disabled:opacity-50 disabled:pointer-events-none cursor-pointer ${variantClass} ${sizeClass} ${className}`}
      {...props}
    >
      {isLoading ? (
        <span className="h-3.5 w-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : (
        icon && <span className="flex items-center">{icon}</span>
      )}
      <span>{children}</span>
    </button>
  );
}
