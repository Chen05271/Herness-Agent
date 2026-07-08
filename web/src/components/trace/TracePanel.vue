<script setup lang="ts">
import { computed, ref } from "vue";
import type { TaskMessage } from "@/types/herness";
import {
  formatTokenCount,
  formatUsageSummary,
  sumTraceUsage,
  usageFromPayload,
} from "@/lib/usage";
import RoleBadge from "./RoleBadge.vue";

const props = defineProps<{
  trace: TaskMessage[];
  isActive: boolean;
  drawer?: boolean;
}>();

defineEmits<{ close: [] }>();

const showExample = ref(false);
const expandedIds = ref<Set<string>>(new Set());

const EXAMPLE_TRACE: TaskMessage[] = [
  {
    id: "ex-1",
    role: "supervisor",
    round_index: 1,
    content: "识别为订单查询，委派 order_worker。",
    payload: { action: "delegate", worker_types: ["order_worker"] },
    created_at: new Date().toISOString(),
  },
  {
    id: "ex-2",
    role: "worker",
    round_index: 1,
    content: "调用 get_order_status，订单已发货。",
    payload: { tool_invocations: [{ tool_name: "get_order_status" }] },
    created_at: new Date().toISOString(),
  },
  {
    id: "ex-3",
    role: "critic",
    round_index: 1,
    content: "事实一致，校验通过。",
    payload: { passed: true },
    created_at: new Date().toISOString(),
  },
];

const displayTrace = computed(() => (showExample.value ? EXAMPLE_TRACE : props.trace));

interface RoundGroup {
  round: number;
  messages: TaskMessage[];
}

const grouped = computed<RoundGroup[]>(() => {
  const map = new Map<number, TaskMessage[]>();
  for (const msg of displayTrace.value) {
    const list = map.get(msg.round_index) ?? [];
    list.push(msg);
    map.set(msg.round_index, list);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a - b)
    .map(([round, messages]) => ({ round, messages }));
});

const isEmpty = computed(
  () => displayTrace.value.length === 0 && !props.isActive && !showExample.value,
);

const totalUsage = computed(() => sumTraceUsage(displayTrace.value));

function stepUsageLabel(msg: TaskMessage): string {
  const usage = usageFromPayload(msg.payload);
  if (!usage || usage.total_tokens <= 0) return "";
  return formatUsageSummary(usage);
}

function toggleExpand(id: string) {
  const next = new Set(expandedIds.value);
  next.has(id) ? next.delete(id) : next.add(id);
  expandedIds.value = next;
}

async function copyJson(msg: TaskMessage) {
  await navigator.clipboard.writeText(JSON.stringify(msg, null, 2));
}
</script>

<template>
  <aside
    class="float-trace flex w-[17rem] shrink-0 flex-col"
    :class="drawer ? 'h-full w-full !m-0 !rounded-none' : 'hidden md:flex'"
  >
    <div class="flex items-center justify-between px-5 py-5">
      <div>
        <h2 class="text-[11px] font-normal uppercase tracking-[0.14em] text-subtle">
          Agent 轨迹
        </h2>
        <p class="mt-1 text-[10px] text-subtle">审计 · 实时</p>
        <p
          v-if="totalUsage.total_tokens > 0"
          class="mt-1.5 text-[10px] theme-accent-muted"
        >
          本次 {{ formatTokenCount(totalUsage.total_tokens) }} tokens
        </p>
      </div>
      <button
        type="button"
        class="text-subtle transition hover:text-muted"
        aria-label="收起"
        @click="$emit('close')"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-4 pb-6">
      <div v-if="isEmpty" class="flex h-full flex-col items-center justify-center px-4 py-14 text-center">
        <div
          class="mb-7 flex h-14 w-14 items-center justify-center rounded-full theme-accent-bg theme-icon-halo animate-theme-halo"
        >
          <svg
            class="h-6 w-6 theme-accent-text"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.25"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728"
            />
          </svg>
        </div>
        <p class="text-xs font-normal leading-[1.75] text-muted">
          发送消息后<br />此处展示 Agent 链路
        </p>
        <button
          type="button"
          class="mt-9 rounded-full px-3 py-1.5 text-[11px] text-subtle transition hover:theme-accent-bg hover:theme-accent-text"
          @click="showExample = true"
        >
          查看示例
        </button>
      </div>

      <div
        v-else-if="displayTrace.length === 0 && isActive"
        class="flex items-center gap-2 px-2 py-3"
      >
        <span class="status-dot animate-pulse-glow" />
        <span class="text-xs text-muted">启动中…</span>
      </div>

      <div v-else class="space-y-6">
        <p
          v-if="showExample"
          class="text-[10px] text-subtle"
        >
          示例预览 ·
          <button class="hover:theme-accent-text" @click="showExample = false">关闭</button>
        </p>

        <div v-for="group in grouped" :key="group.round">
          <p class="mb-3 text-[10px] text-subtle">Round {{ group.round }}</p>
          <div class="space-y-3">
            <div
              v-for="msg in group.messages"
              :key="msg.id"
              class="rounded-xl bg-white/[0.02] px-3 py-3"
            >
              <div class="mb-2 flex items-center justify-between gap-2">
                <RoleBadge :role="msg.role" />
                <div class="flex items-center gap-2 text-[10px] text-subtle">
                  <span
                    v-if="stepUsageLabel(msg)"
                    class="theme-accent-muted"
                  >
                    {{ stepUsageLabel(msg) }}
                  </span>
                  <button class="hover:text-muted" @click="toggleExpand(msg.id)">
                    {{ expandedIds.has(msg.id) ? "收" : "详" }}
                  </button>
                  <button class="hover:text-muted" @click="copyJson(msg)">复制</button>
                </div>
              </div>
              <p
                class="text-[11px] font-normal leading-relaxed text-muted"
                :class="expandedIds.has(msg.id) ? '' : 'line-clamp-3'"
              >
                {{ msg.content }}
              </p>
              <pre
                v-if="expandedIds.has(msg.id)"
                class="mt-2 max-h-32 overflow-auto text-[9px] text-subtle"
              >{{ JSON.stringify(msg.payload, null, 2) }}</pre>
            </div>
          </div>
        </div>

        <div v-if="isActive && !showExample" class="flex items-center gap-2 py-2">
          <span class="shimmer h-px flex-1" />
          <span class="text-[10px] text-subtle">处理中</span>
        </div>
      </div>
    </div>
  </aside>
</template>
