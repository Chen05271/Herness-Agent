<script setup lang="ts">
import type { AgentRole } from "@/types/herness";
import { roleLabel } from "@/lib/persona";

defineProps<{
  role: AgentRole | string;
}>();

const styles: Record<string, string> = {
  supervisor: "text-violet-300/70",
  worker: "text-sky-300/70",
  critic: "theme-accent-text opacity-80",
  orchestrator: "text-muted",
};
</script>

<template>
  <span
    class="text-[10px] font-normal tracking-wide"
    :class="styles[role] ?? styles.orchestrator"
  >
    {{ roleLabel(role) }}
  </span>
</template>
