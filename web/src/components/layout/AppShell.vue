<script setup lang="ts">
import { useBreakpoints, useScrollLock } from "@vueuse/core";
import { computed, watch } from "vue";
import { useChatStore } from "@/stores/chat";
import { useSettingsStore } from "@/stores/settings";
import { themeAttr, type AppTheme } from "@/lib/theme";
import ApiStatusBadge from "@/components/ui/ApiStatusBadge.vue";
import SessionSidebar from "./SessionSidebar.vue";
import TracePanel from "../trace/TracePanel.vue";

const props = withDefaults(
  defineProps<{
    theme: AppTheme;
    title: string;
    subtitle?: string;
    showTrace?: boolean;
    showSessions?: boolean;
  }>(),
  {
    showTrace: true,
    showSessions: true,
  },
);

const chat = useChatStore();
const settings = useSettingsStore();

const breakpoints = useBreakpoints({ md: 768 });
const isMobile = breakpoints.smaller("md");

const traceDrawerOpen = computed(
  () => props.showTrace && settings.tracePanelOpen && isMobile.value,
);

const scrollLock = useScrollLock(document.body);

watch(traceDrawerOpen, (open) => {
  scrollLock.value = open;
});
</script>

<template>
  <div
    class="relative flex h-full overflow-hidden bg-surface-950"
    v-bind="themeAttr(theme)"
  >
    <div class="ambient-bg" aria-hidden="true">
      <div
        class="ambient-orb -left-32 top-[-4rem] h-[36rem] w-[36rem]"
        :style="{ background: 'var(--theme-glow)' }"
      />
      <div
        class="ambient-orb ambient-orb-secondary left-1/3 top-1/2 h-[24rem] w-[24rem] -translate-x-1/2 -translate-y-1/2"
        :style="{ background: 'var(--theme-accent-ring)' }"
      />
      <div
        class="ambient-orb ambient-orb-secondary -right-32 bottom-[-2rem] h-[32rem] w-[32rem]"
        :style="{ background: 'var(--theme-glow-secondary)' }"
      />
    </div>

    <SessionSidebar
      :theme="theme"
      :collapsed="settings.sidebarCollapsed"
      :show-sessions="showSessions"
      @toggle="settings.toggleSidebar()"
    />

    <main class="relative z-10 flex min-w-0 flex-1 flex-col">
      <header
        class="glass-header relative flex shrink-0 flex-col"
      >
        <div class="flex items-center justify-between px-6 py-5 md:px-10">
          <div class="min-w-0">
            <div class="flex items-center gap-3">
              <h1 class="truncate text-[15px] font-normal tracking-wide text-zinc-200/90">
                {{ title }}
              </h1>
              <span v-if="theme === 'consumer'" class="theme-badge animate-edge-breathe">
                C端 · 薄荷绿
              </span>
              <span v-else-if="theme === 'merchant'" class="theme-badge animate-edge-breathe">
                B端 · 淡紫灰
              </span>
            </div>
            <p v-if="subtitle" class="mt-1 truncate text-xs font-normal text-subtle">
              {{ subtitle }}
            </p>
          </div>

          <div class="flex shrink-0 items-center gap-4">
            <ApiStatusBadge :connected="settings.apiConnected" />

            <button
              v-if="showTrace"
              type="button"
              class="rounded-full px-2.5 py-1 text-[11px] font-normal text-subtle transition hover:theme-accent-text"
              :class="settings.tracePanelOpen ? 'theme-accent-bg theme-accent-text !opacity-100' : ''"
              @click="settings.toggleTracePanel()"
            >
              轨迹
            </button>
          </div>
        </div>
        <div class="header-theme-line animate-edge-breathe mx-6 md:mx-10" aria-hidden="true" />
      </header>

      <div class="console-main relative flex min-h-0 flex-1">
        <div class="console-canvas flex min-w-0 flex-1 flex-col">
          <slot />
        </div>
        <TracePanel
          v-if="showTrace && settings.tracePanelOpen && !isMobile"
          :trace="chat.activeTrace"
          :is-active="chat.hasActiveTask"
          @close="settings.closeTracePanel()"
        />
      </div>
    </main>

    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="traceDrawerOpen"
          class="fixed inset-0 z-50 md:hidden"
          role="dialog"
          aria-modal="true"
        >
          <button
            type="button"
            class="absolute inset-0 bg-black/40 backdrop-blur-sm"
            aria-label="关闭"
            @click="settings.closeTracePanel()"
          />
          <Transition
            enter-active-class="transition duration-300 ease-out"
            enter-from-class="translate-x-full"
            enter-to-class="translate-x-0"
            leave-active-class="transition duration-200 ease-in"
            leave-from-class="translate-x-0"
            leave-to-class="translate-x-full"
          >
            <div
              v-if="traceDrawerOpen"
              class="absolute inset-y-3 right-3 w-[min(100vw-1.5rem,20rem)]"
            >
              <TracePanel
                drawer
                :trace="chat.activeTrace"
                :is-active="chat.hasActiveTask"
                @close="settings.closeTracePanel()"
              />
            </div>
          </Transition>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
