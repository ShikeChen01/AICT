import type { RpcResponse, RpcResponseError } from '../../shared/types/rpc';
import { isRpcError } from '../../shared/types/rpc';

const DEFAULT_TIMEOUT_MS = 30_000;

export class RequestTracker {
  private pending = new Map<string, { resolve: (r: RpcResponse) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();

  register(id: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<RpcResponse> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC request ${id} timed out`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  resolve(id: string, response: RpcResponse): void {
    const entry = this.pending.get(id);
    if (!entry) return;
    clearTimeout(entry.timer);
    this.pending.delete(id);
    entry.resolve(response);
  }

  rejectAll(message: string): void {
    for (const [id, entry] of this.pending) {
      clearTimeout(entry.timer);
      entry.reject(new Error(message));
    }
    this.pending.clear();
  }
}
