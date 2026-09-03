'use client';

import { useApp } from '@/hooks/use-app';
import { apiClient, ApiError } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { ArrowUp, Paperclip, StopCircle } from 'lucide-react';
import { useRef, useState } from 'react';

interface ChatComposerProps {
  onSend: (message: string) => Promise<void>;
  disabled?: boolean;
}

const SUGGESTED_QUESTIONS = [
  'Calculate my income tax under both regimes',
  'What deductions can I claim under Section 80C?',
  'Explain my capital gains from this year',
  'Compare old vs new tax regime for my income',
];

export function ChatComposer({ onSend, disabled }: ChatComposerProps) {
  const { selectedYear, isQuerying, setIsQuerying } = useApp();
  const [text, setText] = useState('');
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || isQuerying) return;
    setText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    await onSend(trimmed);
  }

  function handleStop() {
    abortController?.abort();
    setAbortController(null);
    setIsQuerying(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    // Auto-resize
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  }

  return (
    <div className="border-t border-slate-100 bg-white p-4">
      <div className="max-w-3xl mx-auto space-y-3">
        {/* Suggested questions (shown when empty) */}
        {!text && !isQuerying && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => {
                  setText(q);
                  textareaRef.current?.focus();
                }}
                className="text-xs text-slate-500 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-full px-3 py-1.5 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Input area */}
        <div className="flex items-end gap-3 bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 focus-within:border-slate-400 focus-within:bg-white transition-colors">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your taxes..."
            rows={1}
            disabled={disabled || isQuerying}
            className="flex-1 bg-transparent text-sm text-slate-800 placeholder-slate-400 resize-none outline-none min-h-[1.5rem] max-h-40 leading-relaxed disabled:opacity-50"
          />

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-slate-400 font-medium hidden sm:block">
              {selectedYear?.label}
            </span>

            {isQuerying ? (
              <button
                onClick={handleStop}
                className="w-8 h-8 rounded-full bg-red-500 hover:bg-red-600 text-white flex items-center justify-center transition-colors"
              >
                <StopCircle size={14} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!text.trim() || disabled}
                className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center transition-colors',
                  text.trim() && !disabled
                    ? 'bg-slate-900 hover:bg-slate-700 text-white'
                    : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                )}
              >
                <ArrowUp size={14} />
              </button>
            )}
          </div>
        </div>

        <p className="text-xs text-center text-slate-300">
          Tax calculations are deterministic. AI explanations are for guidance only.
        </p>
      </div>
    </div>
  );
}
