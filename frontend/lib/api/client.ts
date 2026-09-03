import type {
  AgentQueryResponse,
  Conversation,
  Document,
  FinancialYear,
  Message,
  UsageInfo,
} from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

class ApiClient {
  private baseUrl: string;
  private authToken: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null) {
    this.authToken = token;
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }
    return { ...headers, ...extra };
  }

  private async request<T>(
    path: string,
    options?: RequestInit
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        ...this.headers(),
        ...(options?.headers as Record<string, string> || {}),
      },
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch {}
      throw new ApiError(detail, response.status);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  // ── Health ───────────────────────────────────────────────
  async health() {
    return this.request<{ status: string; uptime_seconds: number }>('/api/v1/health');
  }

  async usage() {
    return this.request<UsageInfo>('/api/v1/usage');
  }

  // ── Financial Years ───────────────────────────────────────
  async getFinancialYears(): Promise<FinancialYear[]> {
    try {
      return await this.request<FinancialYear[]>('/api/v1/financial-years');
    } catch {
      // Fallback if endpoint not yet implemented
      return [
        { id: '2025-26', label: 'FY 2025-26', year: '2025-26', is_current: true },
        { id: '2024-25', label: 'FY 2024-25', year: '2024-25', is_current: false },
        { id: '2023-24', label: 'FY 2023-24', year: '2023-24', is_current: false },
      ];
    }
  }

  // ── Documents ─────────────────────────────────────────────
  async uploadDocument(file: File, financialYear: string): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('financial_year', financialYear);

    const response = await fetch(`${this.baseUrl}/api/v1/documents/upload`, {
      method: 'POST',
      headers: this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {},
      body: formData,
    });

    if (!response.ok) {
      let detail = `Upload failed: HTTP ${response.status}`;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch {}
      throw new ApiError(detail, response.status);
    }

    return response.json();
  }

  // ── Conversations ─────────────────────────────────────────
  async getConversations(financialYear?: string): Promise<Conversation[]> {
    const params = financialYear ? `?financial_year=${financialYear}` : '';
    try {
      return await this.request<Conversation[]>(`/api/v1/conversations${params}`);
    } catch {
      return [];
    }
  }

  async createConversation(financialYear: string): Promise<Conversation> {
    return this.request<Conversation>('/api/v1/conversations', {
      method: 'POST',
      body: JSON.stringify({ financial_year: financialYear }),
    });
  }

  async getConversation(id: string): Promise<{ conversation: Conversation; messages: Message[] }> {
    return this.request(`/api/v1/conversations/${id}`);
  }

  async deleteConversation(id: string): Promise<void> {
    return this.request(`/api/v1/conversations/${id}`, { method: 'DELETE' });
  }

  // ── Agent ─────────────────────────────────────────────────
  async query(
    question: string,
    financialYear: string,
    sessionId?: string
  ): Promise<AgentQueryResponse> {
    return this.request<AgentQueryResponse>('/api/v1/agent/query', {
      method: 'POST',
      body: JSON.stringify({
        query: question,
        financial_year: financialYear,
        session_id: sessionId,
      }),
    });
  }

  // SSE streaming query
  async *streamQuery(
    question: string,
    financialYear: string,
    sessionId?: string,
    signal?: AbortSignal
  ): AsyncGenerator<{ type: string; content?: string; final_answer?: string; citations?: string[]; usage?: AgentQueryResponse['usage'] }> {
    const response = await fetch(`${this.baseUrl}/api/v1/agent/stream`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({
        query: question,
        financial_year: financialYear,
        session_id: sessionId,
      }),
      signal,
    });

    if (!response.ok) {
      let detail = `Stream failed: HTTP ${response.status}`;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch {}
      throw new ApiError(detail, response.status);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new ApiError('No response body', 500);

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') return;
          try {
            yield JSON.parse(data);
          } catch {}
        }
      }
    }
  }
}

export class ApiError extends Error {
  constructor(
    public detail: string,
    public status: number
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

// Singleton client
export const apiClient = new ApiClient(API_BASE);
