'use client';

import { Sidebar } from '@/components/sidebar/sidebar';
import { useApp } from '@/hooks/use-app';
import { Menu } from 'lucide-react';
import { useState } from 'react';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { selectedYear } = useApp();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-14 border-b border-slate-200 bg-white flex items-center gap-3 px-4 shrink-0">
          {/* Mobile menu toggle */}
          <button
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={18} />
          </button>

          <div className="flex-1">
            <h1 className="text-sm font-semibold text-slate-900">Tax Assistant</h1>
            {selectedYear && (
              <p className="text-xs text-slate-400">{selectedYear.label}</p>
            )}
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 flex flex-col min-h-0">{children}</main>
      </div>
    </div>
  );
}
