'use client';

import { useApp } from '@/hooks/use-app';
import { ArrowUp, StopCircle } from 'lucide-react';
import { useRef, useState } from 'react';

const SUGGESTED_QUESTIONS = [
  'Calculate my income tax under both regimes',
  'What deductions can I claim under Section 80C?',
  'Explain my capital gains from this year',
  'Compare old vs new tax regime for my income',
];

interface ChatComposerProps {
  onSend: (message: string) => Promise<void>;
  disabled?: boolean;
}

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
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  }

  return (
    <div className="p-4" style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
      <div className="max-w-3xl mx-auto space-y-3">
        {!text && !isQuerying && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => { setText(q); textareaRef.current?.focus(); }}
                className="text-xs rounded-full px-3 py-1.5 transition-colors"
                style={{ color: 'var(--text-secondary)', background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        <div
          className="flex items-end gap-3 rounded-2xl px-4 py-3 transition-colors"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your taxes..."
            rows={1}
            disabled={disabled || isQuerying}
            className="flex-1 bg-transparent text-sm resize-none outline-none min-h-[1.5rem] max-h-40 leading-relaxed"
            style={{ color: 'var(--text-primary)', caretColor: 'var(--accent)' }}
          />

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs hidden sm:block" style={{ color: 'var(--text-placeholder)' }}>
              {selectedYear?.label}
            </span>

            {isQuerying ? (
              <button
                onClick={handleStop}
                className="w-8 h-8 rounded-full flex items-center justify-center text-white transition-colors"
                style={{ background: 'var(--error)' }}
              >
                <StopCircle size={14} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!text.trim() || disabled}
                className="w-8 h-8 rounded-full flex items-center justify-center text-white transition-colors"
                style={{ background: text.trim() && !disabled ? 'var(--accent)' : 'var(--border)', cursor: !text.trim() || disabled ? 'not-allowed' : 'pointer' }}
              >
                <ArrowUp size={14} />
              </button>
            )}
          </div>
        </div>

        <p className="text-xs text-center" style={{ color: 'var(--text-placeholder)' }}>
          Tax calculations are deterministic. AI explanations are for guidance only.
        </p>
      </div>
    </div>
  );
}
