'use client';

import { useApp } from '@/hooks/use-app';
import { apiClient, ApiError } from '@/lib/api/client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Message } from '@/types';
import {
  ChatMessage,
  StreamingMessage,
  ThinkingMessage,
} from '@/components/chat/chat-message';
import { ChatComposer } from '@/components/chat/chat-composer';
import { EmptyChat } from '@/components/chat/empty-chat';
import { AlertCircle, RefreshCw } from 'lucide-react';

export function ChatWindow() {
  const {
    selectedYear,
    selectedConversation,
    messages,
    isQuerying,
    setIsQuerying,
    streamingContent,
    setStreamingContent,
    createConversation,
    refreshConversations,
  } = useApp();

  const [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Sync messages from context
  useEffect(() => {
    setLocalMessages(messages);
  }, [messages]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [localMessages, streamingContent, isQuerying]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!selectedYear) return;
      setError('');

      // Create conversation if none selected
      let conversationId = selectedConversation?.id;
      if (!conversationId) {
        const conv = await createConversation();
        if (!conv) {
          setError('Could not create conversation. Please try again.');
          return;
        }
        conversationId = conv.id;
      }

      // Optimistically add user message
      const userMsg: Message = {
        id: Date.now().toString(),
        conversation_id: conversationId,
        role: 'user',
        content: text,
        citations: [],
        created_at: new Date().toISOString(),
      };
      setLocalMessages((prev) => [...prev, userMsg]);
      setIsQuerying(true);
      setStreamingContent('');

      try {
        // Try streaming first, fall back to regular query
        let usedStreaming = false;
        let finalAnswer = '';
        let citations: string[] = [];

        try {
          const stream = apiClient.streamQuery(text, selectedYear.id, conversationId);
          let streamedContent = '';

          for await (const chunk of stream) {
            if (chunk.type === 'token' && chunk.content) {
              streamedContent += chunk.content;
              setStreamingContent(streamedContent);
            } else if (chunk.type === 'done') {
              finalAnswer = chunk.final_answer || streamedContent;
              citations = chunk.citations || [];
              usedStreaming = true;
            }
          }
        } catch {
          // Streaming not available, fall back to regular query
        }

        if (!usedStreaming) {
          const response = await apiClient.query(text, selectedYear.id, conversationId);
          finalAnswer = response.final_answer || 'I was unable to generate a response. Please try again.';
          citations = response.citations || [];
        }

        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          conversation_id: conversationId,
          role: 'assistant',
          content: finalAnswer,
          citations,
          created_at: new Date().toISOString(),
        };

        setLocalMessages((prev) => [...prev, assistantMsg]);
        setStreamingContent('');
        await refreshConversations();
      } catch (err) {
        setStreamingContent('');
        if (err instanceof ApiError) {
          if (err.status === 429) {
            setError("You've reached today's AI usage limit. Your limit will reset tomorrow.");
          } else if (err.status === 503) {
            setError('The AI agent is temporarily unavailable. Please try again shortly.');
          } else {
            setError(err.detail || 'Something went wrong. Please try again.');
          }
        } else {
          setError('Something went wrong. Please try again.');
        }
      } finally {
        setIsQuerying(false);
      }
    },
    [selectedYear, selectedConversation, createConversation, setIsQuerying, setStreamingContent, refreshConversations]
  );

  if (!selectedYear) {
    return (
      <div
        className="flex-1 flex items-center justify-center text-sm"
        style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)' }}
      >
        Select a financial year to get started
      </div>
    );
  }

  const isEmpty = localMessages.length === 0 && !isQuerying;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto" style={{ background: 'var(--bg-base)' }}>
        {isEmpty ? (
          <EmptyChat onSuggestedQuestion={handleSend} />
        ) : (
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            {localMessages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}

            {isQuerying && !streamingContent && <ThinkingMessage />}
            {isQuerying && streamingContent && (
              <StreamingMessage content={streamingContent} />
            )}

            {error && (
              <div
                className="flex items-start gap-3 rounded-xl px-4 py-3"
                style={{ background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--error)' }}
              >
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div className="flex-1 text-sm"><p>{error}</p></div>
                <button onClick={() => setError('')} style={{ color: 'var(--error)', opacity: 0.7 }}>
                  <RefreshCw size={13} />
                </button>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <ChatComposer onSend={handleSend} disabled={false} />
    </div>
  );
}
