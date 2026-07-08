import type { Persona, PersonaContext } from "@/types/herness";

const MERCHANT_USER_ID_RE = /^merchant:[^:]+:ops:[^:]+$/;
const MERCHANT_SESSION_PREFIXES = ["admin-", "merchant-"];
const CONSUMER_SESSION_PREFIX = "consumer-";

export class PersonaValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PersonaValidationError";
  }
}

export function isMerchantUserId(userId: string): boolean {
  return MERCHANT_USER_ID_RE.test(userId.trim());
}

export function validatePersonaIdentity(userId: string, persona: Persona): void {
  const normalized = userId.trim();
  if (!normalized) {
    throw new PersonaValidationError("user_id 不能为空");
  }

  if (persona === "merchant") {
    if (!isMerchantUserId(normalized)) {
      throw new PersonaValidationError(
        "merchant persona 要求 user_id 格式为 merchant:{merchant_id}:ops:{operator_id}",
      );
    }
    return;
  }

  if (isMerchantUserId(normalized)) {
    throw new PersonaValidationError(
      "consumer persona 禁止使用 merchant 命名空间的 user_id",
    );
  }
}

export function defaultSessionId(persona: Persona, userId: string): string {
  if (persona === "merchant") {
    return `admin-${userId}`;
  }
  return `${CONSUMER_SESSION_PREFIX}${userId}`;
}

export function createSessionId(persona: Persona, userId: string): string {
  const suffix = crypto.randomUUID().slice(0, 8);
  if (persona === "merchant") {
    return `admin-${userId}:chat-${suffix}`;
  }
  return `${CONSUMER_SESSION_PREFIX}${userId}:chat-${suffix}`;
}

export function buildConsumerContext(userId?: string): PersonaContext {
  const id = userId?.trim() || `guest-${crypto.randomUUID().slice(0, 8)}`;
  return { persona: "consumer", userId: id };
}

export function buildMerchantContext(
  merchantId: string,
  operatorId: string,
): PersonaContext {
  return {
    persona: "merchant",
    userId: `merchant:${merchantId}:ops:${operatorId}`,
  };
}

export function personaLabel(persona: Persona): string {
  return persona === "merchant" ? "商家运营" : "智能助手";
}

export function roleLabel(role: string): string {
  const map: Record<string, string> = {
    supervisor: "总管",
    worker: "执行",
    critic: "校验",
    orchestrator: "调度",
  };
  return map[role] ?? role;
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "排队中",
    running: "思考中",
    completed: "已完成",
    failed: "失败",
    timeout: "超时",
    aborted: "已中止",
    cancelled: "已取消",
  };
  return map[status] ?? status;
}

export {
  CONSUMER_SESSION_PREFIX,
  MERCHANT_SESSION_PREFIXES,
};
