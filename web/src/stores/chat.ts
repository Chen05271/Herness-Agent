import { defineStore } from "pinia";
import { computed, ref, shallowRef } from "vue";
import { hernessApi } from "@/api/client";
import { subscribeTaskStream } from "@/api/sse";
import {
  clearMessages,
  deleteSession,
  loadMessages,
  loadSessions,
  saveMessage,
  saveSession,
  touchSession,
  updateMessage,
} from "@/db/sessions";
import {
  finalizeAssistantPatch,
  isInFlightStatus,
  isTerminalStatus,
} from "@/lib/messageFinalize";
import { createSessionId, validatePersonaIdentity } from "@/lib/persona";
import { progressFromTraceMessage } from "@/lib/progress";
import type {
  ChatMessage,
  ChatSession,
  Persona,
  TaskMessage,
  TaskStatus,
  TokenUsage,
} from "@/types/herness";
import { useSettingsStore } from "./settings";

function newId(): string {
  return crypto.randomUUID();
}

function sessionTitleFromInput(input: string): string {
  const trimmed = input.trim();
  if (trimmed.length <= 28) return trimmed || "新对话";
  return `${trimmed.slice(0, 28)}…`;
}

export const useChatStore = defineStore("chat", () => {
  const settings = useSettingsStore();

  const persona = ref<Persona>("consumer");
  const sessions = ref<ChatSession[]>([]);
  const activeSessionId = ref<string | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const isSending = ref(false);
  const activeTaskId = ref<string | null>(null);
  const activeTrace = shallowRef<TaskMessage[]>([]);
  const sessionUsage = ref<TokenUsage | null>(null);
  const streamAbort = shallowRef<AbortController | null>(null);
  const error = ref<string | null>(null);

  const activeSession = computed(() =>
    sessions.value.find((s) => s.id === activeSessionId.value) ?? null,
  );

  function patchMessage(
    messageId: string,
    patch: Partial<ChatMessage>,
  ): ChatMessage | undefined {
    const idx = messages.value.findIndex((m) => m.id === messageId);
    if (idx < 0) return undefined;
    const next = { ...messages.value[idx], ...patch };
    messages.value[idx] = next;
    return next;
  }

  const hasActiveTask = computed(
    () =>
      isSending.value ||
      messages.value.some(
        (m) => m.taskId && m.status && isInFlightStatus(m.status),
      ),
  );

  async function repairStaleMessages(
    loaded: ChatMessage[],
    skipTaskId: string | null = null,
  ): Promise<ChatMessage[]> {
    const next = [...loaded];
    let changed = false;

    for (let i = 0; i < next.length; i++) {
      const msg = next[i];
      if (
        msg.role !== "assistant" ||
        !msg.taskId ||
        !isInFlightStatus(msg.status) ||
        msg.taskId === skipTaskId
      ) {
        continue;
      }

      try {
        const result = await hernessApi.getTask(msg.taskId);
        if (!isTerminalStatus(result.status)) {
          continue;
        }

        let trace = msg.trace ?? [];
        if (!trace.length) {
          try {
            const traceResp = await hernessApi.getTaskMessages(msg.taskId);
            trace = traceResp.messages;
          } catch {
            /* 轨迹可选 */
          }
        }

        const repaired = { ...msg, ...finalizeAssistantPatch(result, trace) };
        next[i] = repaired;
        await updateMessage(repaired);
        changed = true;
      } catch (err) {
        const detail = err instanceof Error ? err.message : "";
        if (!detail.startsWith("404:")) {
          continue;
        }
        const repaired: ChatMessage = {
          ...msg,
          status: "failed",
          content: "任务已过期或不存在，请重新发送",
          progressText: undefined,
          error: "任务不存在",
        };
        next[i] = repaired;
        await updateMessage(repaired);
        changed = true;
      }
    }

    return changed ? next : loaded;
  }

  async function refreshSessionUsage(sessionId = activeSessionId.value) {
    if (!sessionId) {
      sessionUsage.value = null;
      return;
    }
    try {
      const ctx = settings.getPersonaContext(persona.value);
      const resp = await hernessApi.getSessionUsage(sessionId, ctx.userId);
      sessionUsage.value = resp.usage;
    } catch {
      sessionUsage.value = null;
    }
  }

  async function init(currentPersona: Persona) {
    persona.value = currentPersona;
    sessions.value = await loadSessions(currentPersona);
    if (sessions.value.length > 0) {
      await selectSession(sessions.value[0].id);
    } else {
      await createNewSession();
    }
  }

  async function createNewSession() {
    const ctx = settings.getPersonaContext(persona.value);
    validatePersonaIdentity(ctx.userId, persona.value);

    const now = new Date().toISOString();
    const session: ChatSession = {
      id: createSessionId(persona.value, ctx.userId),
      persona: persona.value,
      userId: ctx.userId,
      title: "新对话",
      createdAt: now,
      updatedAt: now,
    };

    await saveSession(session);
    sessions.value = [session, ...sessions.value];
    activeSessionId.value = session.id;
    messages.value = [];
    activeTrace.value = [];
    error.value = null;
    sessionUsage.value = null;
  }

  async function selectSession(sessionId: string) {
    if (activeSessionId.value === sessionId) return;
    activeSessionId.value = sessionId;
    messages.value = await repairStaleMessages(await loadMessages(sessionId));
    activeTrace.value = [];
    error.value = null;
    await refreshSessionUsage(sessionId);
  }

  async function removeSession(sessionId: string) {
    await deleteSession(sessionId);
    sessions.value = sessions.value.filter((s) => s.id !== sessionId);
    if (activeSessionId.value === sessionId) {
      if (sessions.value.length > 0) {
        await selectSession(sessions.value[0].id);
      } else {
        await createNewSession();
      }
    }
  }

  async function sendMessage(input: string) {
    const trimmed = input.trim();
    if (!trimmed || !activeSessionId.value || isSending.value) return;

    const sessionId = activeSessionId.value;
    const ctx = settings.getPersonaContext(persona.value);
    validatePersonaIdentity(ctx.userId, persona.value);

    isSending.value = true;
    error.value = null;
    activeTrace.value = [];

    const now = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: newId(),
      sessionId,
      role: "user",
      content: trimmed,
      createdAt: now,
    };
    messages.value.push(userMessage);
    await saveMessage(userMessage);

    const isFirstMessage = messages.value.filter((m) => m.role === "user").length === 1;
    if (isFirstMessage) {
      await touchSession(sessionId, {
        title: sessionTitleFromInput(trimmed),
        updatedAt: now,
      });
      const idx = sessions.value.findIndex((s) => s.id === sessionId);
      if (idx >= 0) {
        sessions.value[idx] = {
          ...sessions.value[idx],
          title: sessionTitleFromInput(trimmed),
          updatedAt: now,
        };
        sessions.value = [...sessions.value].sort(
          (a, b) =>
            new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
        );
      }
    } else {
      await touchSession(sessionId, { updatedAt: now });
    }

    const assistantId = newId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      sessionId,
      role: "assistant",
      content: "",
      status: "pending",
      progressText: "正在理解你的问题",
      trace: [],
      createdAt: new Date().toISOString(),
    };
    messages.value.push(assistantMessage);
    await saveMessage(assistantMessage);

    try {
      const { task_id } = await hernessApi.submitTask({
        user_id: ctx.userId,
        session_id: sessionId,
        input: trimmed,
        metadata: { persona: persona.value },
      });

      activeTaskId.value = task_id;
      patchMessage(assistantId, {
        taskId: task_id,
        status: "running",
        progressText: "正在理解你的问题",
      });
      await updateMessage({
        ...assistantMessage,
        taskId: task_id,
        status: "running",
        progressText: "正在理解你的问题",
      });

      const controller = new AbortController();
      streamAbort.value = controller;
      let latestTrace: TaskMessage[] = [];

      await subscribeTaskStream(task_id, {
        signal: controller.signal,
        onMessage: (msg) => {
          activeTrace.value = [...activeTrace.value, msg];
          latestTrace = [...latestTrace, msg];
          const { progressText, content } = progressFromTraceMessage(msg);
          patchMessage(assistantId, {
            trace: latestTrace,
            status: "running",
            progressText,
            ...(content ? { content } : {}),
          });
        },
        onFinished: (event) => {
          if (isTerminalStatus(event.status)) {
            patchMessage(assistantId, {
              status: event.status,
              progressText: undefined,
            });
          }
        },
        onError: () => {
          /* fallback to polling below */
        },
      });

      const result = await hernessApi.getTask(task_id);
      const trace = latestTrace.length
        ? latestTrace
        : (messages.value.find((m) => m.id === assistantId)?.trace ?? []);
      const finalized = patchMessage(assistantId, {
        ...finalizeAssistantPatch(result, trace),
      });
      if (finalized) {
        await updateMessage(finalized);
      }
      await refreshSessionUsage(sessionId);
      await touchSession(sessionId, { updatedAt: new Date().toISOString() });
    } catch (err) {
      const message = err instanceof Error ? err.message : "发送失败";
      error.value = message;
      const failed = patchMessage(assistantId, {
        status: "failed",
        content: `抱歉，请求失败：${message}`,
        progressText: undefined,
        error: message,
      });
      if (failed) {
        await updateMessage(failed);
      }
    } finally {
      isSending.value = false;
      activeTaskId.value = null;
      streamAbort.value = null;
    }
  }

  async function cancelActiveTask() {
    if (!activeTaskId.value) return;
    try {
      await hernessApi.cancelTask(activeTaskId.value);
      streamAbort.value?.abort();

      const msg = messages.value.find((m) => m.taskId === activeTaskId.value);
      if (msg) {
        const cancelled = patchMessage(msg.id, {
          status: "cancelled" as TaskStatus,
          content: "任务已取消",
          progressText: undefined,
        });
        if (cancelled) {
          await updateMessage(cancelled);
        }
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : "取消失败";
    } finally {
      isSending.value = false;
      activeTaskId.value = null;
    }
  }

  async function clearActiveSession() {
    if (!activeSessionId.value) return;
    const sessionId = activeSessionId.value;
    await clearMessages(sessionId);
    messages.value = [];
    activeTrace.value = [];
    error.value = null;
    await touchSession(sessionId, {
      title: "新对话",
      updatedAt: new Date().toISOString(),
    });
    const idx = sessions.value.findIndex((s) => s.id === sessionId);
    if (idx >= 0) {
      sessions.value[idx] = {
        ...sessions.value[idx],
        title: "新对话",
        updatedAt: new Date().toISOString(),
      };
    }
  }

  function exportActiveSession(): string {
    const lines = messages.value.map((m) => {
      const role = m.role === "user" ? "用户" : "助手";
      return `## ${role}\n\n${m.content}\n`;
    });
    return `# ${activeSession.value?.title ?? "对话导出"}\n\n${lines.join("\n---\n\n")}`;
  }

  async function checkApiHealth() {
    try {
      await hernessApi.healthCheck();
      settings.apiConnected = true;
    } catch {
      settings.apiConnected = false;
    }
  }

  return {
    persona,
    sessions,
    activeSessionId,
    messages,
    isSending,
    activeTaskId,
    activeTrace,
    sessionUsage,
    error,
    activeSession,
    hasActiveTask,
    init,
    createNewSession,
    selectSession,
    removeSession,
    sendMessage,
    cancelActiveTask,
    clearActiveSession,
    exportActiveSession,
    checkApiHealth,
    refreshSessionUsage,
  };
});
