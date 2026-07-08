<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { AppTheme } from "@/lib/theme";
import type { ChatMessage } from "@/types/herness";
import MessageBubble from "./MessageBubble.vue";

const props = defineProps<{
  messages: ChatMessage[];
  promptDisabled?: boolean;
  theme?: AppTheme;
}>();

const emit = defineEmits<{
  selectPrompt: [text: string];
}>();

const CONSUMER_PROMPTS = [
  { label: "查订单", text: "帮我查一下最近的订单状态和物流信息" },
  { label: "产品溯源", text: "介绍一下这款产品的溯源信息和质检报告" },
  { label: "今日推荐", text: "根据季节帮我推荐几款适合购买的商品" },
];

const MERCHANT_PROMPTS = [
  { label: "待发货订单", text: "查询今天待发货和异常订单列表" },
  { label: "库存预警", text: "检查低库存 SKU 并给出补货建议" },
  { label: "营收概览", text: "汇总本周营收、退款率和售后工单趋势" },
];

const quickPrompts = computed(() =>
  props.theme === "merchant" ? MERCHANT_PROMPTS : CONSUMER_PROMPTS,
);

const emptyTitle = computed(() =>
  props.theme === "merchant" ? "商家运营工作台" : "智能助手",
);

const emptyDesc = computed(() =>
  props.theme === "merchant"
    ? "查询订单、库存与运营数据，右侧可查看 Agent 审计轨迹"
    : "商品咨询、订单查询与溯源推荐，多 Agent 协作为你解答",
);

const containerRef = ref<HTMLElement | null>(null);

function handlePromptClick(text: string) {
  if (props.promptDisabled) return;
  emit("selectPrompt", text);
}

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    containerRef.value && (containerRef.value.scrollTop = containerRef.value.scrollHeight);
  },
);

watch(
  () => props.messages.at(-1)?.content,
  async () => {
    await nextTick();
    containerRef.value && (containerRef.value.scrollTop = containerRef.value.scrollHeight);
  },
);

watch(
  () => props.messages.at(-1)?.status,
  async () => {
    await nextTick();
    containerRef.value && (containerRef.value.scrollTop = containerRef.value.scrollHeight);
  },
);

watch(
  () => props.messages.at(-1)?.progressText,
  async () => {
    await nextTick();
    containerRef.value && (containerRef.value.scrollTop = containerRef.value.scrollHeight);
  },
);
</script>

<template>
  <div ref="containerRef" class="flex min-h-0 flex-1 flex-col overflow-y-auto">
    <div
      v-if="messages.length === 0"
      class="flex min-h-0 flex-1 flex-col items-center justify-center px-8 py-12 md:py-16"
    >
      <div class="guide-card animate-theme-breathe">
        <div
          class="mx-auto mb-10 flex h-[4.5rem] w-[4.5rem] items-center justify-center rounded-full theme-accent-bg theme-icon-halo animate-theme-halo"
        >
          <svg
            class="h-8 w-8 theme-accent-text"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.25"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"
            />
          </svg>
        </div>

        <h2 class="text-2xl font-normal tracking-tight text-zinc-100/90 md:text-[1.75rem]">
          {{ emptyTitle }}
        </h2>
        <p class="mt-5 max-w-xs text-center text-sm font-normal leading-[1.75] text-muted">
          {{ emptyDesc }}
        </p>

        <div class="mt-16 flex flex-col items-stretch gap-4 sm:flex-row sm:flex-wrap sm:justify-center">
          <button
            v-for="item in quickPrompts"
            :key="item.text"
            type="button"
            class="prompt-chip disabled:cursor-not-allowed disabled:opacity-30"
            :disabled="promptDisabled"
            @click="handlePromptClick(item.text)"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
    </div>

    <div v-else class="mx-auto max-w-2xl space-y-8 px-6 py-10">
      <MessageBubble v-for="msg in messages" :key="msg.id" :message="msg" />
    </div>
  </div>
</template>
