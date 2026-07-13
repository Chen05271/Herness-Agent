<script setup lang="ts">
import { computed } from "vue";
import { getApiBase, resolveApiUrl } from "@/lib/apiConfig";

const props = defineProps<{
  connected: boolean | null;
}>();

const label = computed(() => {
  if (props.connected === true) return "在线";
  if (props.connected === false) return "离线";
  return "…";
});

const tooltip = computed(() => resolveApiUrl(getApiBase()));
</script>

<template>
  <div
    class="group relative flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-normal text-muted"
    :title="tooltip"
  >
    <span
      class="status-dot"
      :class="
        connected === true
          ? 'animate-pulse-glow'
          : connected === false
            ? '!bg-red-400/60 !opacity-100'
            : '!opacity-30'
      "
    />
    <span class="hidden sm:inline">{{ label }}</span>
    <span
      class="pointer-events-none absolute bottom-full right-0 z-50 mb-2 hidden rounded-lg bg-surface-850/95 px-2 py-1 text-[10px] text-subtle group-hover:block"
    >
      {{ tooltip }}
    </span>
  </div>
</template>
