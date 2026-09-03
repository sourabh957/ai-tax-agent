'use client';

import { useApp } from '@/hooks/use-app';
import { FileText, MessageSquare, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
      <div className="flex-1 flex flex-col items-center justify-center min-h-full px-6 py-12 text-center">
        {/* Icon */}
        <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
          <MessageSquare size={22} className="text-slate-400" />
        </div>

        <h2 className="text-lg font-semibold text-slate-800">
          Your {selectedYear?.label} tax workspace
        </h2>
        <p className="text-sm text-slate-400 mt-2 max-w-xs leading-relaxed">
          Upload your tax documents and ask questions to understand your tax position.
        </p>

        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <Button variant="outline" onClick={() => setUploadOpen(true)}>
            <Upload size={14} />
            Upload document
          </Button>
        </div>

        {/* Suggested questions */}
        <div className="mt-8 w-full max-w-sm space-y-2">
          <p className="text-xs text-slate-400 font-medium uppercase tracking-wider mb-3">
            Suggested questions
          </p>
          <div className="grid gap-2">
            {SUGGESTED.map((q) => (
              <button
                key={q}
                onClick={() => onSuggestedQuestion(q)}
                className="w-full text-left px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm text-slate-600 hover:border-slate-300 hover:bg-slate-50 transition-colors"
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
