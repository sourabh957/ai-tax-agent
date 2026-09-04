'use client';

import { useApp } from '@/hooks/use-app';
import { useAuth } from '@/hooks/use-auth';
import { cn } from '@/lib/utils';
import { CalendarDays, LogOut, MessageSquare, Plus, Upload, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { UploadDocumentModal } from '@/components/documents/upload-modal';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const {
    financialYears,
    selectedYear,
    setSelectedYear,
    conversations,
    selectedConversation,
    setSelectedConversation,
    createConversation,
  } = useApp();
  const { user, logout } = useAuth();
  const router = useRouter();
  const [uploadOpen, setUploadOpen] = useState(false);

  async function handleNewChat() {
    await createConversation();
    onClose();
  }

  function handleLogout() {
    logout();
    router.push('/auth');
  }

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-20 lg:hidden"
          style={{ background: 'rgba(0,0,0,0.6)' }}
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-64 flex-col transition-transform duration-200 ease-in-out lg:static lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        style={{ background: 'var(--bg-surface)', borderRight: '1px solid var(--border)' }}
      >
        {/* Logo */}
        <div
          className="flex items-center justify-between px-4 h-14"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-white"
              style={{ background: 'var(--accent)' }}
            >
              T
            </div>
            <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>Taxly</span>
          </div>
          <button className="lg:hidden p-1 rounded" onClick={onClose} style={{ color: 'var(--text-secondary)' }}>
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {/* Financial Years */}
          <section>
            <p
              className="text-xs font-medium uppercase tracking-wider px-1 mb-2"
              style={{ color: 'var(--text-placeholder)' }}
            >
              Financial Years
            </p>
            <div className="space-y-0.5">
              {financialYears.map((fy) => {
                const active = selectedYear?.id === fy.id;
                return (
                  <button
                    key={fy.id}
                    onClick={() => { setSelectedYear(fy); setSelectedConversation(null); }}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors"
                    style={{
                      background: active ? 'var(--accent)' : 'transparent',
                      color: active ? 'white' : 'var(--text-secondary)',
                    }}
                    onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-hover)'; }}
                    onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
                  >
                    <div className="flex items-center gap-2">
                      <CalendarDays size={14} />
                      <span>{fy.label}</span>
                    </div>
                    {fy.is_current && (
                      <span
                        className="text-xs rounded-full px-1.5 py-0.5"
                        style={{
                          background: active ? 'rgba(255,255,255,0.2)' : 'rgba(52,211,153,0.15)',
                          color: active ? 'white' : 'var(--success)',
                        }}
                      >
                        Current
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>

          {selectedYear && (
            <>
              <div style={{ borderTop: '1px solid var(--border)' }} />

              {/* Documents */}
              <section>
                <div className="flex items-center justify-between px-1 mb-2">
                  <p className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-placeholder)' }}>
                    Documents
                  </p>
                  <button onClick={() => setUploadOpen(true)} style={{ color: 'var(--text-secondary)' }}>
                    <Plus size={14} />
                  </button>
                </div>
                <button
                  onClick={() => setUploadOpen(true)}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
                  style={{
                    color: 'var(--text-secondary)',
                    border: '1px dashed var(--border)',
                    background: 'transparent',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <Upload size={13} />
                  <span>Upload document</span>
                </button>
              </section>

              {/* Conversations */}
              <section>
                <div className="flex items-center justify-between px-1 mb-2">
                  <p className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-placeholder)' }}>
                    Chats
                  </p>
                  <button onClick={handleNewChat} style={{ color: 'var(--text-secondary)' }}>
                    <Plus size={14} />
                  </button>
                </div>
                <div className="space-y-0.5">
                  <button
                    onClick={handleNewChat}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
                    style={{ color: 'var(--text-secondary)', background: 'transparent' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <Plus size={13} />
                    <span>New chat</span>
                  </button>
                  {conversations.slice(0, 15).map((conv) => {
                    const active = selectedConversation?.id === conv.id;
                    return (
                      <button
                        key={conv.id}
                        onClick={() => { setSelectedConversation(conv); onClose(); }}
                        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors"
                        style={{
                          background: active ? 'var(--bg-active)' : 'transparent',
                          color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                        }}
                        onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-hover)'; }}
                        onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
                      >
                        <MessageSquare size={13} className="shrink-0" style={{ color: 'var(--text-placeholder)' }} />
                        <span className="truncate">{conv.title || 'New conversation'}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </>
          )}
        </div>

        {/* Footer — user + logout */}
        <div className="px-3 py-3 space-y-1" style={{ borderTop: '1px solid var(--border)' }}>
          {user && (
            <div
              className="px-3 py-2 rounded-lg text-xs truncate"
              style={{ color: 'var(--text-secondary)', background: 'var(--bg-elevated)' }}
            >
              {user.email}
            </div>
          )}
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
            style={{ color: 'var(--text-secondary)', background: 'transparent' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <LogOut size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <UploadDocumentModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </>
  );
}
