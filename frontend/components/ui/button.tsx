import * as React from 'react';
import { cn } from '@/lib/utils';

export function Button({
  className,
  variant = 'default',
  size = 'default',
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'ghost' | 'outline' | 'destructive' | 'secondary';
  size?: 'default' | 'sm' | 'lg' | 'icon';
}) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 disabled:pointer-events-none disabled:opacity-50',
        {
          'bg-slate-900 text-white hover:bg-slate-800 shadow-sm': variant === 'default',
          'bg-transparent hover:bg-slate-100 text-slate-700': variant === 'ghost',
          'border border-slate-200 bg-white hover:bg-slate-50 text-slate-700': variant === 'outline',
          'bg-red-50 text-red-700 hover:bg-red-100 border border-red-200': variant === 'destructive',
          'bg-slate-100 text-slate-900 hover:bg-slate-200': variant === 'secondary',
        },
        {
          'h-9 px-4 py-2 text-sm': size === 'default',
          'h-7 px-3 text-xs': size === 'sm',
          'h-11 px-6 text-base': size === 'lg',
          'h-9 w-9 p-0': size === 'icon',
        },
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
