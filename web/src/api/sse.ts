import type { StreamEvent, TaskFinishedEvent, TaskMessage } from "@/types/herness";
import { isTaskFinishedEvent } from "@/types/herness";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

export interface TaskStreamOptions {
  onMessage: (message: TaskMessage) => void;
  onFinished: (event: TaskFinishedEvent) => void;
  onError?: (error: Error) => void;
  signal?: AbortSignal;
}

export async function subscribeTaskStream(
  taskId: string,
  options: TaskStreamOptions,
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
  };
  if (API_KEY) {
    headers.Authorization = `Bearer ${API_KEY}`;
  }

  const res = await fetch(`${API_BASE}/v1/tasks/${taskId}/stream`, {
    headers,
    signal: options.signal,
  });

  if (!res.ok) {
    throw new Error(`SSE 连接失败: ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("无法读取 SSE 流");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        let event: StreamEvent;
        try {
          event = JSON.parse(raw) as StreamEvent;
        } catch {
          continue;
        }

        if (isTaskFinishedEvent(event)) {
          options.onFinished(event);
          return;
        }

        options.onMessage(event);
      }
    }
  } catch (err) {
    if (options.signal?.aborted) return;
    options.onError?.(err instanceof Error ? err : new Error(String(err)));
    throw err;
  }
}
