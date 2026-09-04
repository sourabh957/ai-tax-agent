'use client';

import { Sidebar } from '@/components/sidebar/sidebar';
import { useApp } from '@/hooks/use-app';
import { useAuth } from '@/hooks/use-auth';
import { Menu } from 'lucide-react';
import { useState } from 'react';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { selectedYear } = useApp();
  const { user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header
          className="h-14 flex items-center gap-3 px-4 shrink-0"
          style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}
        >
          <button
            className="lg:hidden p-1.5 rounded-lg transition-colors"
            style={{ color: 'var(--text-secondary)' }}
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={18} />
          </button>

          <div className="flex-1">
            <h1 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Tax Assistant
            </h1>
            {selectedYear && (
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {selectedYear.label}
              </p>
            )}
          </div>

          {user && (
            <div
              className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg"
              style={{ color: 'var(--text-secondary)', background: 'var(--bg-elevated)' }}
            >
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium"
                style={{ background: 'var(--accent)', color: 'white' }}
              >
                {(user.name || user.email)[0].toUpperCase()}
              </div>
              <span className="hidden sm:inline truncate max-w-[120px]">{user.name || user.email}</span>
            </div>
          )}
        </header>

        <main className="flex-1 flex flex-col min-h-0">{children}</main>
      </div>
    </div>
  );
}
