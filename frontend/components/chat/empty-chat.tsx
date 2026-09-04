'use client';

import { useApp } from '@/hooks/use-app';
import { MessageSquare, Upload } from 'lucide-react';
import { useState } from 'react';
import { UploadDocumentModal } from '@/components/documents/upload-modal';

const SUGGESTED = [
  'Compare old vs new tax regime',
  'Calculate my taxable income',
  'Check my capital gains tax',
  'What deductions can I claim?',
  'How much TDS has been deducted?',
];

interface EmptyChatProps {
  onSuggestedQuestion: (q: string) => void;
}

export function EmptyChat({ onSuggestedQuestion }: EmptyChatProps) {
  const { selectedYear } = useApp();
  const [uploadOpen, setUploadOpen] = useState(false);

  return (
    <>
      <div
        className="flex-1 flex flex-col items-center justify-center min-h-full px-6 py-12 text-center"
        style={{ background: 'var(--bg-base)' }}
      >
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4"
          style={{ background: 'var(--bg-elevated)' }}
        >
          <MessageSquare size={22} style={{ color: 'var(--accent)' }} />
        </div>

        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          Your {selectedYear?.label} tax workspace
        </h2>
        <p className="text-sm mt-2 max-w-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          Upload your tax documents and ask questions to understand your tax position.
        </p>

        <button
          className="flex items-center gap-2 mt-6 px-5 py-2.5 rounded-xl text-sm font-medium transition-colors"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
          onClick={() => setUploadOpen(true)}
        >
          <Upload size={14} />
          Upload document
        </button>

        <div className="mt-8 w-full max-w-sm space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-placeholder)' }}>
            Suggested questions
          </p>
          <div className="grid gap-2">
            {SUGGESTED.map((q) => (
              <button
                key={q}
                onClick={() => onSuggestedQuestion(q)}
                className="w-full text-left px-4 py-3 rounded-xl text-sm transition-colors"
                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </div>

      <UploadDocumentModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </>
  );
}
