<script setup lang="ts">
defineProps<{
  progressText?: string;
}>();
</script>

<template>
  <div class="flex items-center gap-2 py-1">
    <span class="flex gap-1">
      <span
        v-for="i in 3"
        :key="i"
        class="h-2 w-2 rounded-full bg-accent-400"
        :style="{
          animation: 'pulse-glow 1.4s ease-in-out infinite',
          animationDelay: `${(i - 1) * 0.16}s`,
        }"
      />
    </span>
    <span class="text-sm text-zinc-400">
      {{ progressText ?? "思考中" }}…
    </span>
  </div>
</template>
