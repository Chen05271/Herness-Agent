<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useEventListener, useScrollLock } from "@vueuse/core";
import { computed, watch } from "vue";
import { useConfirmStore } from "@/stores/confirm";

const store = useConfirmStore();
const { open, options } = storeToRefs(store);

const scrollLock = useScrollLock(document.body);

watch(open, (isOpen) => {
  scrollLock.value = isOpen;
});

const isDanger = computed(() => options.value?.tone === "danger");

useEventListener(window, "keydown", (e: KeyboardEvent) => {
  if (!open.value) return;
  if (e.key === "Escape") {
    e.preventDefault();
    store.dismiss();
  }
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    store.accept();
  }
});
</script>

<template>
  <Teleport to="body">
    <Transition name="confirm">
      <div
        v-if="open && options"
        class="confirm-root"
        role="alertdialog"
        aria-modal="true"
        :aria-labelledby="'confirm-title'"
        :aria-describedby="'confirm-message'"
      >
        <button
          type="button"
          class="confirm-backdrop"
          aria-label="关闭"
          @click="store.dismiss()"
        />

        <div
          class="confirm-panel"
          :class="{ 'confirm-panel--danger': isDanger }"
        >
          <div class="confirm-accent-line" aria-hidden="true" />

          <div class="confirm-body">
            <div
              class="confirm-icon"
              :class="{ 'confirm-icon--danger': isDanger }"
              aria-hidden="true"
            >
              <svg
                v-if="isDanger"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
                />
              </svg>
              <svg
                v-else
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                />
              </svg>
            </div>

            <h2 id="confirm-title" class="confirm-title">
              {{ options.title }}
            </h2>
            <p id="confirm-message" class="confirm-message">
              {{ options.message }}
            </p>
            <p v-if="options.detail" class="confirm-detail">
              {{ options.detail }}
            </p>
          </div>

          <div class="confirm-actions">
            <button
              type="button"
              class="confirm-btn confirm-btn--ghost"
              @click="store.dismiss()"
            >
              {{ options.cancelLabel }}
            </button>
            <button
              type="button"
              class="confirm-btn"
              :class="isDanger ? 'confirm-btn--danger' : 'confirm-btn--primary'"
              autofocus
              @click="store.accept()"
            >
              {{ options.confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
