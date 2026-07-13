<script setup lang="ts">
import type { QuotaWarning } from "@/lib/quota";

defineProps<{
  warning: QuotaWarning;
}>();
</script>

<template>
  <div
    class="quota-warning-bar mx-auto max-w-2xl px-6"
    :class="warning.progress.status === 'exhausted' ? 'is-exhausted' : 'is-warning'"
  >
    <p class="text-center text-[11px]">{{ warning.message }}</p>
  </div>
</template>
