/**
 * WebSocket/HTTP bridge to cloud LLM providers. Handles tool calls and results.
 * High-level stub - full implementation when agent endpoint is defined.
 */

import type { AgentWorkStation } from './AgentWorkStation';

export class AgentBridge {
  private workStation: AgentWorkStation;
  private connection: WebSocket | null = null;

  constructor(workStation: AgentWorkStation) {
    this.workStation = workStation;
  }

  async connect(_endpoint: string): Promise<void> {
    // Stub: establish WebSocket when endpoint and protocol are defined
  }

  disconnect(): void {
    if (this.connection) {
      this.connection.close();
      this.connection = null;
    }
  }

  handleToolCall(_name: string, _args: unknown): unknown {
    // Stub: map tool name + args to CommandRegistry.execute and return result
    return null;
  }

  sendToolResult(_callId: string, _result: unknown): void {
    // Stub: send result back to LLM over connection
  }
}
