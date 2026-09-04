'use client';

import { timeAgo } from '@/lib/utils';
import type { Message } from '@/types';
import { ExternalLink, User } from 'lucide-react';

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-white text-xs font-bold"
          style={{ background: 'var(--accent)' }}
        >
          T
        </div>
      )}

      <div className={`max-w-[80%] space-y-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className="rounded-2xl px-4 py-3 text-sm leading-relaxed"
          style={isUser
            ? { background: 'var(--accent)', color: 'white', borderTopRightRadius: '4px' }
            : { background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-primary)', borderTopLeftRadius: '4px' }
          }
        >
          <MessageContent content={message.content} isUser={isUser} />
        </div>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="px-1 space-y-1">
            <p className="text-xs font-medium" style={{ color: 'var(--text-placeholder)' }}>Sources</p>
            <div className="flex flex-wrap gap-1.5">
              {message.citations.map((citation, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 text-xs rounded-full px-2.5 py-0.5"
                  style={{ color: 'var(--text-secondary)', background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                >
                  <ExternalLink size={9} />
                  {citation}
                </span>
              ))}
            </div>
          </div>
        )}

        <p className="text-xs px-1" style={{ color: 'var(--text-placeholder)' }}>
          {timeAgo(message.created_at)}
        </p>
      </div>

      {isUser && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5"
          style={{ background: 'var(--bg-elevated)' }}
        >
          <User size={13} style={{ color: 'var(--text-secondary)' }} />
        </div>
      )}
    </div>
  );
}

export function StreamingMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3 justify-start">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-white text-xs font-bold"
        style={{ background: 'var(--accent)' }}
      >
        T
      </div>
      <div className="max-w-[80%]">
        <div
          className="rounded-2xl px-4 py-3 text-sm leading-relaxed"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-primary)', borderTopLeftRadius: '4px' }}
        >
          {content}
          <span className="inline-block w-0.5 h-4 ml-0.5 animate-pulse" style={{ background: 'var(--accent)' }} />
        </div>
      </div>
    </div>
  );
}

export function ThinkingMessage() {
  return (
    <div className="flex gap-3 justify-start">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-white text-xs font-bold"
        style={{ background: 'var(--accent)' }}
      >
        T
      </div>
      <div
        className="rounded-2xl px-4 py-3"
        style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderTopLeftRadius: '4px' }}
      >
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:-0.3s]" style={{ background: 'var(--text-secondary)' }} />
          <div className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:-0.15s]" style={{ background: 'var(--text-secondary)' }} />
          <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-secondary)' }} />
        </div>
      </div>
    </div>
  );
}

function MessageContent({ content, isUser }: { content: string; isUser: boolean }) {
  if (isUser) return <p>{content}</p>;

  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    if (line.startsWith('### ')) {
      elements.push(<h3 key={key++} className="font-semibold mt-2 mb-1" style={{ color: 'var(--text-primary)' }}>{line.slice(4)}</h3>);
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={key++} className="font-semibold mt-3 mb-1" style={{ color: 'var(--text-primary)' }}>{line.slice(3)}</h2>);
    } else if (line.startsWith('**') && line.endsWith('**')) {
      elements.push(<p key={key++} className="font-semibold">{line.slice(2, -2)}</p>);
    } else if (line.startsWith('- ') || line.startsWith('• ')) {
      elements.push(
        <div key={key++} className="flex gap-2 items-start">
          <span className="mt-0.5" style={{ color: 'var(--accent)' }}>•</span>
          <span>{line.slice(2)}</span>
        </div>
      );
    } else if (line.trim() === '') {
      elements.push(<div key={key++} className="h-2" />);
    } else {
      elements.push(<p key={key++}>{line}</p>);
    }
  }

  return <div className="space-y-0.5">{elements}</div>;
}
