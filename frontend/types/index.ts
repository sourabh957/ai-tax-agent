// Core application types

export interface FinancialYear {
  id: string;
  label: string;
  year: string;
  is_current: boolean;
}

export interface Document {
  id: string;
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  financial_year: string;
  extraction_status: 'uploading' | 'processing' | 'ready' | 'failed';
  extracted_chars: number;
  created_at: string;
  message?: string;
}

export interface Conversation {
  id: string;
  financial_year: string;
  title: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: string[];
  created_at: string;
}

export interface AgentQueryResponse {
  request_id: string;
  status: 'completed' | 'failed' | 'timeout' | 'running';
  final_answer: string | null;
  citations: string[];
  reasoning: string;
  usage: {
    model_id: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    llm_call_count: number;
    tool_call_count: number;
    iteration_count: number;
    latency_ms: number;
    estimated_cost_usd: number;
  };
  warnings: string[];
}

export interface TaxCalculationResult {
  financial_year: string;
  regime: string;
  gross_income: number;
  standard_deduction: number;
  taxable_income: number;
  total_tax: number;
  effective_rate_pct: number;
}

export interface RegimeComparison {
  new_regime: TaxCalculationResult;
  old_regime: TaxCalculationResult;
  recommended_regime: 'new' | 'old';
  tax_saving_by_choosing_recommended: number;
  explanation: string;
}

export interface UsageInfo {
  user_id: string;
  requests_today: number;
  daily_limit: number;
  requests_remaining: number;
}

export interface ApiError {
  detail: string;
  status: number;
}
