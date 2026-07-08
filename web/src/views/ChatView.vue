<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppShell from "@/components/layout/AppShell.vue";
import Composer from "@/components/chat/Composer.vue";
import MessageList from "@/components/chat/MessageList.vue";
import { useChatStore } from "@/stores/chat";
import { useConfirmStore } from "@/stores/confirm";
import { useSettingsStore } from "@/stores/settings";

const chat = useChatStore();
const confirm = useConfirmStore();
const settings = useSettingsStore();
const route = useRoute();
const router = useRouter();

onMounted(async () => {
  await chat.init("consumer");
  await chat.checkApiHealth();

  const sessionId = route.params.sessionId as string | undefined;
  if (sessionId && chat.sessions.some((s) => s.id === sessionId)) {
    await chat.selectSession(sessionId);
  } else if (sessionId) {
    router.replace("/chat");
  } else if (chat.activeSessionId) {
    router.replace(`/chat/${chat.activeSessionId}`);
  }
});

watch(
  () => chat.activeSessionId,
  (id) => {
    if (id && route.params.sessionId !== id) {
      router.replace(`/chat/${id}`);
    }
  },
);

async function handleSend(text: string) {
  await chat.sendMessage(text);
}

async function handleCancel() {
  await chat.cancelActiveTask();
}

async function handleClear() {
  if (!chat.messages.length) return;
  const ok = await confirm.confirm({
    title: "清空对话",
    message: "确定清空当前对话？",
    detail: "此操作不可撤销，所有消息将被永久删除。",
    confirmLabel: "清空",
    tone: "default",
  });
  if (!ok) return;
  await chat.clearActiveSession();
}

function handleExport() {
  if (!chat.messages.length) return;
  const content = chat.exportActiveSession();
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `herness-chat-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <AppShell
    theme="consumer"
    title="Consumer · 多 Agent 对话"
    subtitle="智能助手"
  >
    <div class="chat-workspace">
      <MessageList
        theme="consumer"
        :messages="chat.messages"
        :prompt-disabled="chat.isSending"
        @select-prompt="handleSend"
      />

      <div
        v-if="chat.error || settings.apiConnected === false"
        class="mx-auto mb-1 max-w-2xl px-6"
      >
        <div
          v-if="settings.apiConnected === false"
          class="py-2 text-center text-[11px] text-subtle"
        >
          无法连接后端 · 请运行
          <code class="font-mono text-muted">.\run-api.ps1</code>
        </div>
        <div v-if="chat.error" class="py-2 text-center text-[11px] text-red-300/50">
          {{ chat.error }}
        </div>
      </div>

      <Composer
        :is-sending="chat.isSending"
        :show-cancel="chat.hasActiveTask"
        :can-clear="chat.messages.length > 0"
        :can-export="chat.messages.length > 0"
        placeholder="输入你的商品咨询、订单查询问题…"
        @send="handleSend"
        @cancel="handleCancel"
        @clear="handleClear"
        @export="handleExport"
      />
    </div>
  </AppShell>
</template>
