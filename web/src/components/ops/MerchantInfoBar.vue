<script setup lang="ts">
import { ref } from "vue";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();

const copiedField = ref<string | null>(null);
const userId = `merchant:${settings.merchantId}:ops:${settings.operatorId}`;

async function copyValue(field: string, value: string) {
  await navigator.clipboard.writeText(value);
  copiedField.value = field;
  window.setTimeout(() => {
    if (copiedField.value === field) copiedField.value = null;
  }, 1500);
}

function persistSettings() {
  settings.persistIdentity();
}
</script>

<template>
  <div class="shrink-0 border-b border-white/[0.03] px-6 py-4 md:px-10">
    <div class="glass-card mx-auto max-w-2xl px-5 py-4 md:px-6 md:py-5">
      <div class="grid gap-4 sm:grid-cols-3 sm:gap-5">
        <div>
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.12em] text-subtle">商家 ID</span>
            <button
              type="button"
              class="text-[10px] text-subtle transition hover:theme-accent-text"
              @click="copyValue('merchant', settings.merchantId)"
            >
              {{ copiedField === "merchant" ? "已复制" : "复制" }}
            </button>
          </div>
          <input
            v-model="settings.merchantId"
            class="theme-input w-full px-3 py-2.5 font-mono text-sm font-normal text-zinc-300/90"
            @change="persistSettings"
          />
        </div>

        <div>
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.12em] text-subtle">操作员</span>
            <button
              type="button"
              class="text-[10px] text-subtle transition hover:theme-accent-text"
              @click="copyValue('operator', settings.operatorId)"
            >
              {{ copiedField === "operator" ? "已复制" : "复制" }}
            </button>
          </div>
          <input
            v-model="settings.operatorId"
            class="theme-input w-full px-3 py-2.5 font-mono text-sm font-normal text-zinc-300/90"
            @change="persistSettings"
          />
        </div>

        <div>
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.12em] text-subtle">user_id</span>
            <button
              type="button"
              class="text-[10px] text-subtle transition hover:theme-accent-text"
              @click="copyValue('userId', userId)"
            >
              {{ copiedField === "userId" ? "已复制" : "复制" }}
            </button>
          </div>
          <p class="truncate px-1 py-2.5 font-mono text-xs font-normal text-muted" :title="userId">
            {{ userId }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
