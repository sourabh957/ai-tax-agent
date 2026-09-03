'use client';

import { cn, timeAgo } from '@/lib/utils';
import type { Message } from '@/types';
import { ExternalLink, User } from 'lucide-react';

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-slate-900 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-white text-xs font-bold">T</span>
        </div>
      )}

      <div className={cn('max-w-[80%] space-y-1.5', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'rounded-2xl px-4 py-3 text-sm leading-relaxed',
            isUser
              ? 'bg-slate-900 text-white rounded-tr-sm'
              : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm shadow-sm'
          )}
        >
          <MessageContent content={message.content} isUser={isUser} />
        </div>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="px-1 space-y-1">
            <p className="text-xs text-slate-400 font-medium">Sources</p>
            <div className="flex flex-wrap gap-1.5">
              {message.citations.map((citation, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-full px-2.5 py-0.5"
                >
                  <ExternalLink size={9} />
                  {citation}
                </span>
              ))}
            </div>
          </div>
        )}

        <p className="text-xs text-slate-300 px-1">
          {timeAgo(message.created_at)}
        </p>
      </div>

      {isUser && (
        <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center shrink-0 mt-0.5">
          <User size={13} className="text-slate-500" />
        </div>
      )}
    </div>
  );
}

export function StreamingMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3 justify-start">
      <div className="w-7 h-7 rounded-full bg-slate-900 flex items-center justify-center shrink-0 mt-0.5">
        <span className="text-white text-xs font-bold">T</span>
      </div>
      <div className="max-w-[80%]">
        <div className="bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm shadow-sm px-4 py-3 text-sm leading-relaxed">
          {content}
          <span className="inline-block w-1 h-4 bg-slate-400 ml-0.5 animate-pulse" />
        </div>
      </div>
    </div>
  );
}

export function ThinkingMessage() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="w-7 h-7 rounded-full bg-slate-900 flex items-center justify-center shrink-0 mt-0.5">
        <span className="text-white text-xs font-bold">T</span>
      </div>
      <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm shadow-sm px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
          <div className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
          <div className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" />
        </div>
      </div>
    </div>
  );
}

function MessageContent({ content, isUser }: { content: string; isUser: boolean }) {
  if (isUser) return <p>{content}</p>;

  // Basic markdown-like rendering for assistant messages
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    if (line.startsWith('### ')) {
      elements.push(<h3 key={key++} className="font-semibold text-slate-900 mt-2 mb-1">{line.slice(4)}</h3>);
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={key++} className="font-semibold text-slate-900 mt-3 mb-1">{line.slice(3)}</h2>);
    } else if (line.startsWith('**') && line.endsWith('**')) {
      elements.push(<p key={key++} className="font-semibold">{line.slice(2, -2)}</p>);
    } else if (line.startsWith('- ') || line.startsWith('• ')) {
      elements.push(
        <div key={key++} className="flex gap-2 items-start">
          <span className="text-slate-400 mt-0.5">•</span>
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
