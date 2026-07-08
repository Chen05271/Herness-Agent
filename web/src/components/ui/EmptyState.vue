<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
  icon?: "chat" | "graph" | "trace" | "search" | "upload";
}>();
</script>

<template>
  <div class="flex flex-col items-center justify-center px-8 py-16 text-center md:py-20">
    <div
      class="mb-8 flex h-14 w-14 items-center justify-center rounded-full theme-accent-bg"
      style="box-shadow: 0 0 48px var(--theme-glow)"
    >
      <slot name="icon">
        <svg
          class="h-6 w-6 theme-accent-text opacity-50"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="1.25"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"
          />
        </svg>
      </slot>
    </div>
    <h3 class="text-[15px] font-normal text-zinc-200/80">{{ title }}</h3>
    <p v-if="description" class="mt-3 max-w-sm text-[12px] font-normal leading-relaxed text-subtle">
      {{ description }}
    </p>
    <div v-if="$slots.actions" class="mt-8 flex flex-wrap justify-center gap-3">
      <slot name="actions" />
    </div>
  </div>
</template>
