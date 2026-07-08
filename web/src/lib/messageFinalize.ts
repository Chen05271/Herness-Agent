import { resolveUsage } from "@/lib/usage";
import { answerFromTrace } from "@/lib/progress";
import type {
  ChatMessage,
  TaskMessage,
  TaskStatus,
  TaskStatusResponse,
} from "@/types/herness";

export const IN_FLIGHT_STATUSES: TaskStatus[] = ["pending", "running"];

export const TERMINAL_STATUSES: TaskStatus[] = [
  "completed",
  "failed",
  "timeout",
  "aborted",
  "cancelled",
];

export function isInFlightStatus(status?: TaskStatus): boolean {
  return Boolean(status && IN_FLIGHT_STATUSES.includes(status));
}

export function isTerminalStatus(status?: TaskStatus): boolean {
  return Boolean(status && TERMINAL_STATUSES.includes(status));
}

/** 从任务 API 响应推导聊天气泡最终文案。 */
export function resolveTaskAnswer(
  result: TaskStatusResponse,
  trace: TaskMessage[] = [],
): string {
  if (result.status === "completed") {
    return result.answer || answerFromTrace(trace) || "任务未返回有效答案";
  }
  return result.error || answerFromTrace(trace) || "任务未返回有效答案";
}

/** 任务终态 → 助手消息 patch。 */
export function finalizeAssistantPatch(
  result: TaskStatusResponse,
  trace: TaskMessage[] = [],
): Partial<ChatMessage> {
  return {
    status: result.status,
    content: resolveTaskAnswer(result, trace),
    progressText: undefined,
    error: result.status !== "completed" ? result.error || undefined : undefined,
    trace,
    usage: resolveUsage(result.usage, trace),
  };
}
