<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useChatStore } from "@/stores/chat";
import { useConfirmStore } from "@/stores/confirm";
import { useSettingsStore } from "@/stores/settings";
import { formatTokenCount } from "@/lib/usage";
import type { AppTheme } from "@/lib/theme";
import type { Persona } from "@/types/herness";

const props = defineProps<{
  theme: AppTheme;
  collapsed: boolean;
  showSessions?: boolean;
}>();

const emit = defineEmits<{ toggle: [] }>();

const chat = useChatStore();
const confirm = useConfirmStore();
const settings = useSettingsStore();
const route = useRoute();
const router = useRouter();

const basePath = computed(() =>
  props.theme === "merchant" ? "/ops" : props.theme === "rag" ? "/rag" : "/chat",
);

const navItems = [
  { path: "/chat", label: "智能助手", theme: "consumer" as AppTheme },
  { path: "/ops", label: "商家运营", theme: "merchant" as AppTheme },
  { path: "/rag", label: "RAG", theme: "rag" as AppTheme },
  { path: "/settings", label: "设置", theme: "settings" as AppTheme },
];

const showSessionPanel = computed(() => props.showSessions !== false);

const sessionUsageLabel = computed(() => {
  if (!settings.showTokenUsage) return "";
  const usage = chat.sessionUsage;
  if (!usage || usage.total_tokens <= 0) return "";
  return `${formatTokenCount(usage.total_tokens)} tokens`;
});

function isActive(path: string): boolean {
  return route.path.startsWith(path);
}

function formatDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 86400000) return "今天";
  if (diff < 172800000) return "昨天";
  return new Date(iso).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

async function handleNewChat() {
  const persona: Persona = props.theme === "merchant" ? "merchant" : "consumer";
  if (chat.persona !== persona) await chat.init(persona);
  await chat.createNewSession();
  router.push(basePath.value);
}

async function handleSelect(sessionId: string) {
  await chat.selectSession(sessionId);
  router.push(`${basePath.value}/${sessionId}`);
}

async function handleDelete(sessionId: string, e: Event) {
  e.stopPropagation();
  const ok = await confirm.confirm({
    title: "删除对话",
    message: "确定删除此对话？",
    detail: "删除后无法恢复该会话记录。",
    confirmLabel: "删除",
    tone: "danger",
  });
  if (!ok) return;
  await chat.removeSession(sessionId);
  router.push(
    chat.activeSessionId ? `${basePath.value}/${chat.activeSessionId}` : basePath.value,
  );
}
</script>

<template>
  <aside
    class="glass-nav relative z-20 flex shrink-0 flex-col transition-all duration-300"
    :class="collapsed ? 'w-[3.75rem]' : 'w-[13.5rem]'"
  >
    <div
      class="flex items-center px-4 py-6"
      :class="collapsed ? 'justify-center' : 'justify-between'"
    >
      <div v-if="!collapsed" class="min-w-0">
        <p class="text-[13px] font-normal tracking-wide text-zinc-300/80">Herness</p>
        <p class="mt-0.5 text-[10px] text-subtle">Agent Console</p>
      </div>
      <button
        type="button"
        class="rounded-lg p-1 text-subtle transition hover:text-muted"
        :aria-label="collapsed ? '展开' : '收起'"
        @click="emit('toggle')"
      >
        <svg
          class="h-4 w-4 transition"
          :class="collapsed ? 'rotate-180' : ''"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
        </svg>
      </button>
    </div>

    <nav class="space-y-1.5 px-3">
      <RouterLink
        v-for="link in navItems"
        :key="link.path"
        :to="link.path"
        class="group relative flex items-center gap-3 rounded-xl px-3 py-3 transition"
        :class="
          isActive(link.path)
            ? 'bg-white/[0.04] theme-accent-ring'
            : 'text-muted hover:bg-white/[0.02] hover:text-zinc-300/70'
        "
        :title="collapsed ? link.label : undefined"
      >
        <span
          v-if="isActive(link.path)"
          class="absolute bottom-2 left-0 top-2 w-0.5 rounded-full theme-accent-bar animate-edge-breathe"
        />
        <span class="flex h-5 w-5 shrink-0 items-center justify-center opacity-60 group-hover:opacity-90">
          <svg
            v-if="link.theme === 'consumer'"
            class="h-[18px] w-[18px]"
            :class="isActive(link.path) ? 'theme-accent-text opacity-100' : ''"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"
            />
          </svg>
          <svg
            v-else-if="link.theme === 'merchant'"
            class="h-[18px] w-[18px]"
            :class="isActive(link.path) ? 'theme-accent-text opacity-100' : ''"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349M3.75 21V9.349m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016a3.001 3.001 0 003.75.614m-16.5 0a3.004 3.004 0 01-.621-4.72L4.318 3.44A1.5 1.5 0 015.378 3h13.243a1.5 1.5 0 011.06.44l1.19 1.189a3 3 0 01-.621 4.72m-13.5 8.65h3.75a.75.75 0 00.75-.75V13.5a.75.75 0 00-.75-.75H6.75a.75.75 0 00-.75.75v3.75c0 .414.336.75.75.75z"
            />
          </svg>
          <svg
            v-else-if="link.theme === 'rag'"
            class="h-[18px] w-[18px]"
            :class="isActive(link.path) ? 'theme-accent-text opacity-100' : ''"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <svg
            v-else-if="link.theme === 'settings'"
            class="h-[18px] w-[18px]"
            :class="isActive(link.path) ? 'theme-accent-text opacity-100' : ''"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
            />
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
        </span>
        <span v-if="!collapsed" class="truncate text-[13px] font-normal">{{ link.label }}</span>
      </RouterLink>
    </nav>

    <div v-if="showSessionPanel" class="mt-6 px-3">
      <button
        type="button"
        class="theme-btn-ghost flex w-full items-center justify-center gap-2 px-3 py-2.5 text-[13px]"
        @click="handleNewChat"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        <span v-if="!collapsed">新对话</span>
      </button>
    </div>

    <div v-if="showSessionPanel && !collapsed" class="mt-8 flex min-h-0 flex-1 flex-col px-3 pb-6">
      <p class="mb-3 px-1 text-[10px] uppercase tracking-[0.14em] text-subtle">历史</p>
      <p v-if="chat.sessions.length === 0" class="px-1 py-4 text-xs text-subtle">暂无记录</p>
      <ul class="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        <li v-for="session in chat.sessions" :key="session.id">
          <button
            type="button"
            class="group flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition"
            :class="
              chat.activeSessionId === session.id
                ? 'bg-white/[0.04]'
                : 'hover:bg-white/[0.02]'
            "
            @click="handleSelect(session.id)"
          >
            <p
              class="min-w-0 flex-1 truncate text-[13px] font-normal"
              :class="chat.activeSessionId === session.id ? 'text-zinc-200/90' : 'text-muted'"
            >
              {{ session.title }}
            </p>
            <button
              type="button"
              class="shrink-0 text-subtle opacity-0 transition hover:text-red-400/70 group-hover:opacity-100"
              aria-label="删除"
              @click="handleDelete(session.id, $event)"
            >
              ×
            </button>
          </button>
          <p class="px-3 pb-1 text-[10px] text-subtle">{{ formatDate(session.updatedAt) }}</p>
        </li>
      </ul>
      <p
        v-if="chat.activeSessionId && sessionUsageLabel"
        class="mt-4 border-t border-white/[0.04] px-1 pt-4 text-[10px] theme-accent-muted"
      >
        本会话 {{ sessionUsageLabel }}
      </p>
    </div>
  </aside>
</template>
