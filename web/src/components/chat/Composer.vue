<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{
  disabled?: boolean;
  isSending?: boolean;
  showCancel?: boolean;
  placeholder?: string;
  canClear?: boolean;
  canExport?: boolean;
  minimal?: boolean;
}>();

const emit = defineEmits<{
  send: [text: string];
  cancel: [];
  clear: [];
  export: [];
}>();

const input = ref("");

function handleSubmit() {
  const text = input.value.trim();
  if (!text || props.disabled || props.isSending) return;
  emit("send", text);
  input.value = "";
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    input.value = "";
    return;
  }
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSubmit();
  }
}

onMounted(() => {
  /* Esc handled on textarea */
});

onUnmounted(() => {
  /* noop */
});
</script>

<template>
  <div class="float-composer-wrap shrink-0">
    <div class="mx-auto max-w-2xl">
      <slot name="error" />

      <div
        v-if="!minimal && (canClear || canExport)"
        class="mb-3 flex items-center justify-end gap-3"
      >
        <button
          v-if="canClear"
          type="button"
          class="text-[11px] text-subtle transition hover:text-muted"
          @click="emit('clear')"
        >
          清空
        </button>
        <button
          v-if="canExport"
          type="button"
          class="text-[11px] text-subtle transition hover:text-muted"
          @click="emit('export')"
        >
          导出
        </button>
      </div>

      <div class="float-composer flex items-end gap-3 p-3 md:p-4">
        <textarea
          v-model="input"
          data-composer
          rows="1"
          :placeholder="placeholder ?? '输入消息…'"
          :disabled="disabled || isSending"
          class="max-h-36 min-h-[52px] flex-1 resize-none bg-transparent px-2 py-3 text-[15px] font-normal leading-relaxed text-zinc-200 placeholder:text-subtle outline-none disabled:opacity-40"
          @keydown="handleKeydown"
        />

        <div class="flex shrink-0 items-center gap-2 pb-1">
          <button
            v-if="showCancel"
            type="button"
            class="rounded-full px-3 py-1.5 text-[11px] text-red-400/70 transition hover:text-red-300"
            @click="emit('cancel')"
          >
            停止
          </button>

          <button
            type="button"
            class="flex h-10 w-10 items-center justify-center rounded-full transition"
            :class="
              input.trim() && !disabled && !isSending
                ? 'theme-btn-primary shadow-lg'
                : 'bg-white/[0.03] text-subtle cursor-not-allowed'
            "
            :disabled="!input.trim() || disabled || isSending"
            aria-label="发送"
            @click="handleSubmit"
          >
            <svg
              v-if="!isSending"
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
              />
            </svg>
            <svg v-else class="h-4 w-4 animate-spin opacity-60" fill="none" viewBox="0 0 24 24">
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="3"
              />
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
