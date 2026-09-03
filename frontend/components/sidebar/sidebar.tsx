'use client';

import { useApp } from '@/hooks/use-app';
import { cn } from '@/lib/utils';
import {
  CalendarDays,
  ChevronRight,
  FileText,
  LogOut,
  MessageSquare,
  Plus,
  Settings,
  Upload,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { UploadDocumentModal } from '@/components/documents/upload-modal';
import { Button } from '@/components/ui/button';

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

  const [uploadOpen, setUploadOpen] = useState(false);

  async function handleNewChat() {
    await createConversation();
    onClose();
  }

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/20 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-white border-r border-slate-200 transition-transform duration-200 ease-in-out lg:static lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-4 h-14 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-slate-900 flex items-center justify-center">
              <span className="text-white text-xs font-bold">T</span>
            </div>
            <span className="font-semibold text-slate-900">Taxly</span>
          </div>
          <button
            className="lg:hidden p-1 rounded text-slate-400 hover:text-slate-600"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {/* Financial Years */}
          <section>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider px-1 mb-2">
              Financial Years
            </p>
            <div className="space-y-0.5">
              {financialYears.map((fy) => (
                <button
                  key={fy.id}
                  onClick={() => {
                    setSelectedYear(fy);
                    setSelectedConversation(null);
                  }}
                  className={cn(
                    'w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors',
                    selectedYear?.id === fy.id
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-50'
                  )}
                >
                  <div className="flex items-center gap-2">
                    <CalendarDays size={14} />
                    <span>{fy.label}</span>
                  </div>
                  {fy.is_current && (
                    <span
                      className={cn(
                        'text-xs rounded-full px-1.5 py-0.5',
                        selectedYear?.id === fy.id
                          ? 'bg-white/20 text-white'
                          : 'bg-emerald-50 text-emerald-700'
                      )}
                    >
                      Current
                    </span>
                  )}
                </button>
              ))}
            </div>
          </section>

          {selectedYear && (
            <>
              {/* Divider */}
              <div className="border-t border-slate-100" />

              {/* Documents */}
              <section>
                <div className="flex items-center justify-between px-1 mb-2">
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Documents
                  </p>
                  <button
                    onClick={() => setUploadOpen(true)}
                    className="text-slate-400 hover:text-slate-700 transition-colors"
                    title="Upload document"
                  >
                    <Plus size={14} />
                  </button>
                </div>
                <button
                  onClick={() => setUploadOpen(true)}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-50 transition-colors border border-dashed border-slate-200"
                >
                  <Upload size={13} />
                  <span>Upload document</span>
                </button>
              </section>

              {/* Conversations */}
              <section>
                <div className="flex items-center justify-between px-1 mb-2">
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Chats
                  </p>
                  <button
                    onClick={handleNewChat}
                    className="text-slate-400 hover:text-slate-700 transition-colors"
                    title="New chat"
                  >
                    <Plus size={14} />
                  </button>
                </div>

                {conversations.length === 0 ? (
                  <button
                    onClick={handleNewChat}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-50 transition-colors"
                  >
                    <MessageSquare size={13} />
                    <span>New chat</span>
                  </button>
                ) : (
                  <div className="space-y-0.5">
                    <button
                      onClick={handleNewChat}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-50 transition-colors"
                    >
                      <Plus size={13} />
                      <span>New chat</span>
                    </button>
                    {conversations.slice(0, 10).map((conv) => (
                      <button
                        key={conv.id}
                        onClick={() => {
                          setSelectedConversation(conv);
                          onClose();
                        }}
                        className={cn(
                          'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors group',
                          selectedConversation?.id === conv.id
                            ? 'bg-slate-100 text-slate-900'
                            : 'text-slate-600 hover:bg-slate-50'
                        )}
                      >
                        <MessageSquare size={13} className="shrink-0 text-slate-400" />
                        <span className="truncate">{conv.title || 'New conversation'}</span>
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-100 px-3 py-3 space-y-1">
          <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-50 transition-colors">
            <Settings size={14} />
            <span>Settings</span>
          </button>
          <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-50 transition-colors">
            <LogOut size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <UploadDocumentModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </>
  );
}
