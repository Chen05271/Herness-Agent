<script setup lang="ts">
import { computed } from "vue";
import type { TokenUsage } from "@/types/herness";
import { formatTokenCount } from "@/lib/usage";
import { computeQuotaProgress, formatQuotaLine } from "@/lib/quota";

const props = defineProps<{
  label: string;
  usage: TokenUsage | null;
  limit: number;
  subtitle?: string;
}>();

const progress = computed(() =>
  props.usage
    ? computeQuotaProgress(props.usage.total_tokens, props.limit)
    : null,
);

const statusClass = computed(() => {
  if (!progress.value) return "";
  if (progress.value.status === "exhausted") return "is-exhausted";
  if (progress.value.status === "warning") return "is-warning";
  return "";
});
</script>

<template>
  <div class="usage-quota-card rounded-xl bg-white/[0.02] p-4">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="text-[13px] text-zinc-200/90">{{ label }}</p>
        <p v-if="subtitle" class="mt-1 truncate font-mono text-[11px] text-subtle">
          {{ subtitle }}
        </p>
      </div>
      <p v-if="usage" class="shrink-0 text-right text-xs text-muted">
        <span class="font-mono">{{ formatTokenCount(usage.total_tokens) }}</span>
        <span class="text-subtle"> tokens</span>
      </p>
      <p v-else class="shrink-0 text-xs text-subtle">—</p>
    </div>

    <div v-if="usage" class="mt-3 grid grid-cols-3 gap-2 text-[10px] text-subtle">
      <span>输入 {{ formatTokenCount(usage.input_tokens) }}</span>
      <span>输出 {{ formatTokenCount(usage.output_tokens) }}</span>
      <span class="text-right">合计 {{ formatTokenCount(usage.total_tokens) }}</span>
    </div>

    <div v-if="progress" class="mt-4">
      <div class="mb-2 flex items-center justify-between text-[11px]">
        <span class="text-subtle">配额进度</span>
        <span
          class="font-mono"
          :class="
            progress.status === 'exhausted'
              ? 'text-red-300/80'
              : progress.status === 'warning'
                ? 'text-amber-200/80'
                : 'text-muted'
          "
        >
          {{ formatQuotaLine(progress) }}
        </span>
      </div>
      <div class="quota-progress-track">
        <div
          class="quota-progress-bar"
          :class="statusClass"
          :style="{ width: `${progress.percent}%` }"
        />
      </div>
      <p class="mt-2 text-[10px] text-subtle">
        剩余 {{ formatTokenCount(progress.remaining) }} tokens
      </p>
    </div>
    <p v-else-if="limit <= 0" class="mt-4 text-[11px] text-subtle">未设置配额上限</p>
  </div>
</template>
