<script setup lang="ts">
const modelValue = defineModel<boolean>({ required: true });

defineProps<{
  label: string;
  description?: string;
  disabled?: boolean;
}>();
</script>

<template>
  <div class="flex items-start justify-between gap-4">
    <div class="min-w-0 flex-1">
      <p class="text-[13px] font-normal text-zinc-200/90">{{ label }}</p>
      <p v-if="description" class="mt-1 text-xs leading-relaxed text-subtle">
        {{ description }}
      </p>
    </div>
    <button
      type="button"
      role="switch"
      class="settings-toggle shrink-0"
      :class="modelValue ? 'is-on' : ''"
      :aria-checked="modelValue"
      :aria-label="label"
      :disabled="disabled"
      @click="modelValue = !modelValue"
    >
      <span class="settings-toggle-knob" />
    </button>
  </div>
</template>
