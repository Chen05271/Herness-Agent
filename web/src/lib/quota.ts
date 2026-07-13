import type { TokenUsage } from "@/types/herness";

export interface QuotaProgress {
  used: number;
  limit: number;
  remaining: number;
  percent: number;
  status: "ok" | "warning" | "exhausted";
}

export function computeQuotaProgress(
  used: number,
  limit: number,
  warningRatio = 0.8,
): QuotaProgress | null {
  if (limit <= 0) return null;
  const remaining = Math.max(limit - used, 0);
  const percent = Math.min((used / limit) * 100, 100);
  let status: QuotaProgress["status"] = "ok";
  if (used >= limit) status = "exhausted";
  else if (used / limit >= warningRatio) status = "warning";
  return { used, limit, remaining, percent, status };
}

export function formatQuotaLine(progress: QuotaProgress): string {
  return `${progress.used.toLocaleString()} / ${progress.limit.toLocaleString()} tokens`;
}

export interface QuotaWarning {
  scope: "session" | "user";
  message: string;
  progress: QuotaProgress;
}

export function resolveQuotaWarning(
  sessionUsage: TokenUsage | null,
  userUsage: TokenUsage | null,
  sessionLimit: number,
  userLimit: number,
  warningRatio = 0.8,
): QuotaWarning | null {
  const sessionProgress = sessionUsage
    ? computeQuotaProgress(sessionUsage.total_tokens, sessionLimit, warningRatio)
    : null;
  if (sessionProgress && sessionProgress.status !== "ok") {
    return {
      scope: "session",
      progress: sessionProgress,
      message:
        sessionProgress.status === "exhausted"
          ? "本会话 token 配额已用尽，请新建对话或联系管理员"
          : `本会话 token 已使用 ${Math.round(sessionProgress.percent)}%，接近配额上限`,
    };
  }

  const userProgress = userUsage
    ? computeQuotaProgress(userUsage.total_tokens, userLimit, warningRatio)
    : null;
  if (userProgress && userProgress.status !== "ok") {
    return {
      scope: "user",
      progress: userProgress,
      message:
        userProgress.status === "exhausted"
          ? "账号 token 配额已用尽，请联系管理员"
          : `账号 token 已使用 ${Math.round(userProgress.percent)}%，接近配额上限`,
    };
  }

  return null;
}

export function formatSubmitError(err: unknown): string {
  const raw = err instanceof Error ? err.message : "发送失败";
  if (!raw.includes("429")) return raw;
  if (raw.includes("会话")) {
    return "本会话 token 配额已用尽，请新建对话或联系管理员";
  }
  if (raw.includes("用户")) {
    return "账号 token 配额已用尽，请联系管理员";
  }
  return "Token 配额已用尽，请稍后再试";
}
