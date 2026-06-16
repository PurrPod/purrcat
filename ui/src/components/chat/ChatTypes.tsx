// src/components/chat/ChatTypes.ts
export interface Message {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
  tool_calls?: any[];
}

export interface EventItem {
  type: string;
  time: string;
  content: string;
}

export interface Session {
  id: string;
  alias: string;
  messages_count: number;
  updated_at: string;
}