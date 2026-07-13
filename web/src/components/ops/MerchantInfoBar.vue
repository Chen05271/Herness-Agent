<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();

const copiedField = ref<string | null>(null);

const userId = computed(
  () => `merchant:${settings.merchantId}:ops:${settings.operatorId}`,
);

async function copyValue(field: string, value: string) {
  await navigator.clipboard.writeText(value);
  copiedField.value = field;
  window.setTimeout(() => {
    if (copiedField.value === field) copiedField.value = null;
  }, 1500);
}
</script>

<template>
  <div class="shrink-0 border-b border-white/[0.03] px-6 py-4 md:px-10">
    <div class="glass-card mx-auto max-w-2xl px-5 py-4 md:px-6 md:py-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="grid min-w-0 flex-1 gap-4 sm:grid-cols-3 sm:gap-5">
          <div>
            <span class="text-[10px] uppercase tracking-[0.12em] text-subtle">商家 ID</span>
            <p class="mt-2 truncate font-mono text-sm text-zinc-300/90">
              {{ settings.merchantId }}
            </p>
          </div>

          <div>
            <span class="text-[10px] uppercase tracking-[0.12em] text-subtle">操作员</span>
            <p class="mt-2 truncate font-mono text-sm text-zinc-300/90">
              {{ settings.operatorId }}
            </p>
          </div>

          <div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-[10px] uppercase tracking-[0.12em] text-subtle">user_id</span>
              <button
                type="button"
                class="text-[10px] text-subtle transition hover:theme-accent-text"
                @click="copyValue('userId', userId)"
              >
                {{ copiedField === "userId" ? "已复制" : "复制" }}
              </button>
            </div>
            <p class="mt-2 truncate font-mono text-xs text-muted" :title="userId">
              {{ userId }}
            </p>
          </div>
        </div>

        <RouterLink
          to="/settings#settings-identity"
          class="theme-btn-ghost shrink-0 px-3 py-1.5 text-[11px]"
        >
          编辑身份
        </RouterLink>
      </div>
    </div>
  </div>
</template>
