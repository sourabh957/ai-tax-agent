'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { Conversation, Document, FinancialYear, Message, UsageInfo } from '@/types';
import { apiClient } from '@/lib/api/client';
import { getFinancialYears } from '@/lib/utils';

interface AppContextValue {
  // Financial Year
  financialYears: FinancialYear[];
  selectedYear: FinancialYear | null;
  setSelectedYear: (fy: FinancialYear) => void;

  // Conversations
  conversations: Conversation[];
  selectedConversation: Conversation | null;
  messages: Message[];
  setSelectedConversation: (c: Conversation | null) => void;
  createConversation: () => Promise<Conversation | null>;
  refreshConversations: () => Promise<void>;

  // Chat state
  isQuerying: boolean;
  setIsQuerying: (v: boolean) => void;
  streamingContent: string;
  setStreamingContent: (v: string) => void;

  // Usage
  usage: UsageInfo | null;
  refreshUsage: () => Promise<void>;

  // Documents
  documents: Document[];
  addDocument: (doc: Document) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [financialYears] = useState<FinancialYear[]>(getFinancialYears());
  const [selectedYear, setSelectedYear] = useState<FinancialYear | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);

  // Set default financial year
  useEffect(() => {
    const current = financialYears.find((fy) => fy.is_current) || financialYears[0];
    setSelectedYear(current);
  }, [financialYears]);

  // Load conversations when year changes
  useEffect(() => {
    if (selectedYear) {
      refreshConversations();
    }
  }, [selectedYear]);

  const refreshConversations = useCallback(async () => {
    if (!selectedYear) return;
    try {
      const data = await apiClient.getConversations(selectedYear.id);
      setConversations(data);
    } catch {
      setConversations([]);
    }
  }, [selectedYear]);

  const createConversation = useCallback(async (): Promise<Conversation | null> => {
    if (!selectedYear) return null;
    try {
      const conv = await apiClient.createConversation(selectedYear.id);
      setConversations((prev) => [conv, ...prev]);
      setSelectedConversation(conv);
      setMessages([]);
      return conv;
    } catch {
      return null;
    }
  }, [selectedYear]);

  const refreshUsage = useCallback(async () => {
    try {
      const data = await apiClient.usage();
      setUsage(data);
    } catch {
      setUsage(null);
    }
  }, []);

  const addDocument = useCallback((doc: Document) => {
    setDocuments((prev) => [doc, ...prev]);
  }, []);

  // Load selected conversation messages
  useEffect(() => {
    if (!selectedConversation) {
      setMessages([]);
      return;
    }
    apiClient
      .getConversation(selectedConversation.id)
      .then(({ messages: msgs }) => setMessages(msgs))
      .catch(() => setMessages([]));
  }, [selectedConversation]);

  return (
    <AppContext.Provider
      value={{
        financialYears,
        selectedYear,
        setSelectedYear,
        conversations,
        selectedConversation,
        messages,
        setSelectedConversation,
        createConversation,
        refreshConversations,
        isQuerying,
        setIsQuerying,
        streamingContent,
        setStreamingContent,
        usage,
        refreshUsage,
        documents,
        addDocument,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
