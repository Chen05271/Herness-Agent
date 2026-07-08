<script setup lang="ts">
defineProps<{
  text: string;
  title?: string;
}>();
</script>

<template>
  <span class="group relative inline-flex">
    <button
      type="button"
      class="inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] text-zinc-500 ring-1 ring-white/10 transition hover:bg-white/5 hover:text-zinc-300"
      :aria-label="title ?? '帮助说明'"
    >
      ?
    </button>
    <span
      role="tooltip"
      class="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-xl border border-white/10 bg-surface-850 px-3 py-2.5 text-left text-[11px] leading-relaxed text-zinc-300 opacity-0 shadow-2xl transition group-hover:opacity-100 group-focus-within:opacity-100"
    >
      <span v-if="title" class="mb-1 block text-xs font-semibold text-zinc-100">{{
        title
      }}</span>
      {{ text }}
    </span>
  </span>
</template>
