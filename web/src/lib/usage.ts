import type { TaskMessage, TokenUsage } from "@/types/herness";

const EMPTY_USAGE: TokenUsage = {
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
};

function isTokenUsage(value: unknown): value is TokenUsage {
  if (!value || typeof value !== "object") return false;
  const u = value as Record<string, unknown>;
  return (
    typeof u.input_tokens === "number" &&
    typeof u.output_tokens === "number" &&
    typeof u.total_tokens === "number"
  );
}

export function usageFromPayload(payload: Record<string, unknown>): TokenUsage | null {
  const raw = payload.usage;
  return isTokenUsage(raw) ? raw : null;
}

export function sumTraceUsage(trace: TaskMessage[]): TokenUsage {
  return trace.reduce<TokenUsage>((acc, msg) => {
    const step = usageFromPayload(msg.payload);
    if (!step) return acc;
    return {
      input_tokens: acc.input_tokens + step.input_tokens,
      output_tokens: acc.output_tokens + step.output_tokens,
      total_tokens: acc.total_tokens + step.total_tokens,
      requests: (acc.requests ?? 0) + (step.requests ?? 0),
      tool_calls: (acc.tool_calls ?? 0) + (step.tool_calls ?? 0),
    };
  }, { ...EMPTY_USAGE });
}

export function resolveUsage(
  usage: TokenUsage | undefined,
  trace: TaskMessage[] = [],
): TokenUsage {
  if (usage && usage.total_tokens > 0) return usage;
  const fromTrace = sumTraceUsage(trace);
  return fromTrace.total_tokens > 0 ? fromTrace : usage ?? EMPTY_USAGE;
}

export function formatTokenCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function formatUsageSummary(usage: TokenUsage): string {
  if (usage.total_tokens <= 0) return "";
  return `${formatTokenCount(usage.total_tokens)} tokens · ↑${formatTokenCount(usage.input_tokens)} ↓${formatTokenCount(usage.output_tokens)}`;
}
