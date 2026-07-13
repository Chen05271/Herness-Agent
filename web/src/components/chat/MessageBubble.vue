<script setup lang="ts">
import { computed } from "vue";
import type { ChatMessage } from "@/types/herness";
import { statusLabel } from "@/lib/persona";
import { renderMarkdown } from "@/lib/markdown";
import { formatUsageSummary, resolveUsage } from "@/lib/usage";
import { useSettingsStore } from "@/stores/settings";
import StreamingIndicator from "./StreamingIndicator.vue";

const props = defineProps<{
  message: ChatMessage;
}>();

const settings = useSettingsStore();

const isUser = computed(() => props.message.role === "user");
const isRunning = computed(
  () =>
    props.message.role === "assistant" &&
    props.message.status &&
    ["pending", "running"].includes(props.message.status),
);
const isError = computed(
  () =>
    props.message.status &&
    ["failed", "timeout", "aborted", "cancelled"].includes(props.message.status),
);

const renderedContent = computed(() => {
  if (!props.message.content) return "";
  return renderMarkdown(props.message.content);
});

const usageSummary = computed(() => {
  if (!settings.showTokenUsage) return "";
  const usage = resolveUsage(props.message.usage, props.message.trace ?? []);
  return formatUsageSummary(usage);
});
</script>

<template>
  <div
    class="animate-fade-up flex gap-4"
    :class="isUser ? 'flex-row-reverse' : 'flex-row'"
  >
    <div
      class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-normal"
      :class="
        isUser
          ? 'bg-white/[0.04] text-muted'
          : 'theme-accent-bg theme-accent-text opacity-70'
      "
    >
      {{ isUser ? "你" : "AI" }}
    </div>

    <div
      class="chat-message-bubble max-w-[min(640px,82%)] rounded-2xl px-5 py-4"
      :class="
        isUser
          ? 'bg-white/[0.04] text-zinc-200/90'
          : isError
            ? 'bg-red-500/[0.04] text-red-200/80'
            : 'glass-card text-zinc-200/85'
      "
    >
      <StreamingIndicator
        v-if="isRunning"
        :progress-text="message.progressText"
      />

      <div
        v-if="renderedContent"
        class="prose-agent text-[14px] font-normal"
        :class="isRunning ? 'mt-3 opacity-90' : ''"
        v-html="renderedContent"
      />

      <p
        v-else-if="!isUser && !isRunning && !message.content"
        class="text-[13px] text-subtle"
      >
        等待响应…
      </p>

      <div
        v-if="message.status && !isUser && !isRunning"
        class="mt-3 flex items-center gap-3 pt-3"
        style="box-shadow: inset 0 1px 0 rgba(255,255,255,0.03)"
      >
        <span
          class="text-[10px] font-normal"
          :class="
            message.status === 'completed'
              ? 'theme-accent-text opacity-60'
              : 'text-red-300/50'
          "
        >
          {{ statusLabel(message.status) }}
        </span>
        <span v-if="message.trace?.length" class="text-[10px] text-subtle">
          {{ message.trace.length }} 条审计
        </span>
        <span v-if="usageSummary" class="text-[10px] text-subtle">
          {{ usageSummary }}
        </span>
      </div>
    </div>
  </div>
</template>
