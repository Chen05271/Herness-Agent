<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import AppShell from "@/components/layout/AppShell.vue";
import SettingsToggle from "@/components/settings/SettingsToggle.vue";
import UsageQuotaCard from "@/components/settings/UsageQuotaCard.vue";
import HelpTip from "@/components/ui/HelpTip.vue";
import { hernessApi } from "@/api/client";
import {
  getDefaultApiBase,
  getDefaultApiKey,
  resolveApiUrl,
} from "@/lib/apiConfig";
import {
  buildConsumerContext,
  buildMerchantContext,
  createSessionId,
} from "@/lib/persona";
import { useChatStore } from "@/stores/chat";
import { useConfirmStore } from "@/stores/confirm";
import { useSettingsStore } from "@/stores/settings";
import { loadMessages, loadSessions } from "@/db/sessions";
import type { TokenUsage } from "@/types/herness";

const settings = useSettingsStore();
const chat = useChatStore();
const confirm = useConfirmStore();

const sections = [
  { id: "connection", label: "连接与服务" },
  { id: "identity", label: "身份与角色" },
  { id: "usage", label: "用量与配额" },
  { id: "interface", label: "界面与体验" },
  { id: "data", label: "数据与隐私" },
  { id: "about", label: "关于" },
] as const;

type SectionId = (typeof sections)[number]["id"];

const activeSection = ref<SectionId>("connection");
const draftApiBase = ref(settings.apiBase);
const draftApiKey = ref(settings.apiKey);
const draftConsumerUserId = ref(settings.consumerUserId);
const draftMerchantId = ref(settings.merchantId);
const draftOperatorId = ref(settings.operatorId);
const showApiKey = ref(false);
const isTestingConnection = ref(false);
const connectionMessage = ref<{ type: "success" | "error"; text: string } | null>(
  null,
);
const saveMessage = ref<string | null>(null);
const copiedField = ref<string | null>(null);
const isExporting = ref(false);
const isRefreshingUsage = ref(false);
const usageError = ref<string | null>(null);
const consumerUsage = ref<TokenUsage | null>(null);
const merchantUsage = ref<TokenUsage | null>(null);
const activeSessionUsage = ref<TokenUsage | null>(null);

const userSessionLimit = computed(
  () => settings.publicConfig?.limits.token_budget_per_user ?? 0,
);
const sessionTokenLimit = computed(
  () => settings.publicConfig?.limits.token_budget_per_session ?? 0,
);
const usageLoadedLabel = computed(() => {
  if (!settings.publicConfigLoadedAt) return "尚未刷新";
  return new Date(settings.publicConfigLoadedAt).toLocaleString("zh-CN");
});
const featureLabels = computed(() => {
  const features = settings.publicConfig?.features;
  if (!features) return [];
  return [
    { key: "RAG", enabled: features.rag_enabled },
    { key: "Dreaming", enabled: features.dreaming_enabled },
    { key: "Hereness", enabled: features.hereness_enabled },
    { key: "Agri", enabled: features.agri_commerce_enabled },
    { key: "OTEL", enabled: features.otel_enabled },
  ];
});

const resolvedApiUrl = computed(() => resolveApiUrl(draftApiBase.value));
const consumerUserIdPreview = computed(
  () => buildConsumerContext(draftConsumerUserId.value).userId,
);
const merchantUserIdPreview = computed(
  () => buildMerchantContext(draftMerchantId.value, draftOperatorId.value).userId,
);
const consumerSessionExample = computed(
  () => `${createSessionId("consumer", consumerUserIdPreview.value)}`,
);
const lastCheckedLabel = computed(() => {
  if (!settings.apiLastCheckedAt) return "尚未检测";
  return new Date(settings.apiLastCheckedAt).toLocaleString("zh-CN");
});

onMounted(async () => {
  await chat.checkApiHealth();
  await refreshUsageStats();
});

async function refreshUsageStats() {
  isRefreshingUsage.value = true;
  usageError.value = null;
  try {
    await settings.fetchPublicConfig(true);
    const consumerId = buildConsumerContext(settings.consumerUserId).userId;
    const merchantId = buildMerchantContext(
      settings.merchantId,
      settings.operatorId,
    ).userId;
    const requests = [
      hernessApi.getUserUsage(consumerId),
      hernessApi.getUserUsage(merchantId),
    ];
    if (chat.activeSessionId) {
      const ctx = settings.getPersonaContext(chat.persona);
      requests.push(
        hernessApi.getSessionUsage(chat.activeSessionId, ctx.userId),
      );
    }
    const results = await Promise.allSettled(requests);
    consumerUsage.value =
      results[0].status === "fulfilled" ? results[0].value.usage : null;
    merchantUsage.value =
      results[1].status === "fulfilled" ? results[1].value.usage : null;
    if (chat.activeSessionId) {
      activeSessionUsage.value =
        results[2]?.status === "fulfilled" ? results[2].value.usage : null;
    } else {
      activeSessionUsage.value = null;
    }
    if (results.every((item) => item.status === "rejected")) {
      usageError.value = "无法加载用量数据，请检查连接";
    }
  } catch (err) {
    usageError.value = err instanceof Error ? err.message : "刷新失败";
  } finally {
    isRefreshingUsage.value = false;
  }
}

function flashSave(text: string) {
  saveMessage.value = text;
  window.setTimeout(() => {
    saveMessage.value = null;
  }, 2400);
}

async function copyValue(field: string, value: string) {
  await navigator.clipboard.writeText(value);
  copiedField.value = field;
  window.setTimeout(() => {
    if (copiedField.value === field) copiedField.value = null;
  }, 1500);
}

function scrollToSection(id: SectionId) {
  activeSection.value = id;
  document.getElementById(`settings-${id}`)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function saveConnection() {
  settings.apiBase = draftApiBase.value.trim() || getDefaultApiBase();
  settings.apiKey = draftApiKey.value;
  settings.persistConnection();
  draftApiBase.value = settings.apiBase;
  draftApiKey.value = settings.apiKey;
  await testConnection(true);
  flashSave("连接设置已保存");
}

function resetConnectionDraft() {
  settings.resetConnectionSettings();
  draftApiBase.value = settings.apiBase;
  draftApiKey.value = settings.apiKey;
  connectionMessage.value = null;
  flashSave("已恢复默认连接配置");
}

async function testConnection(silent = false) {
  isTestingConnection.value = true;
  if (!silent) connectionMessage.value = null;
  try {
    settings.persistConnection();
    await chat.checkApiHealth();
    if (settings.apiConnected) {
      connectionMessage.value = { type: "success", text: "连接成功" };
    } else {
      connectionMessage.value = { type: "error", text: "无法连接后端服务" };
    }
  } catch (err) {
    settings.markApiChecked(false);
    connectionMessage.value = {
      type: "error",
      text: err instanceof Error ? err.message : "连接测试失败",
    };
  } finally {
    isTestingConnection.value = false;
  }
}

async function saveIdentity() {
  settings.consumerUserId = draftConsumerUserId.value.trim();
  settings.merchantId = draftMerchantId.value.trim();
  settings.operatorId = draftOperatorId.value.trim();
  settings.persistIdentity();
  draftConsumerUserId.value = settings.consumerUserId;
  draftMerchantId.value = settings.merchantId;
  draftOperatorId.value = settings.operatorId;
  flashSave("身份设置已保存");
  await refreshUsageStats();
}

async function regenerateConsumerId() {
  const ok = await confirm.confirm({
    title: "生成新用户 ID",
    message: "确定生成新的 C 端用户 ID？",
    detail: "已有本地会话仍绑定旧 ID，新对话将使用新身份。",
    confirmLabel: "生成",
    tone: "default",
  });
  if (!ok) return;
  settings.regenerateConsumerUserId();
  draftConsumerUserId.value = settings.consumerUserId;
  flashSave("已生成新用户 ID");
}

function resetIdentityDraft() {
  settings.resetIdentitySettings();
  draftConsumerUserId.value = settings.consumerUserId;
  draftMerchantId.value = settings.merchantId;
  draftOperatorId.value = settings.operatorId;
  flashSave("身份已恢复默认");
}

function saveUiSettings() {
  settings.persistUiSettings();
  flashSave("界面设置已保存");
}

function resetUiSettings() {
  settings.resetUiSettings();
  flashSave("界面设置已恢复默认");
}

async function clearConsumerSessions() {
  const ok = await confirm.confirm({
    title: "清空 C 端对话",
    message: "确定删除所有智能助手对话？",
    detail: "此操作不可恢复，仅清除本地 IndexedDB 数据。",
    confirmLabel: "清空",
    tone: "danger",
  });
  if (!ok) return;
  await chat.purgePersonaSessions("consumer");
  flashSave("C 端对话已清空");
}

async function clearMerchantSessions() {
  const ok = await confirm.confirm({
    title: "清空 B 端对话",
    message: "确定删除所有商家运营对话？",
    detail: "此操作不可恢复，仅清除本地 IndexedDB 数据。",
    confirmLabel: "清空",
    tone: "danger",
  });
  if (!ok) return;
  await chat.purgePersonaSessions("merchant");
  flashSave("B 端对话已清空");
}

async function exportAllSessions() {
  isExporting.value = true;
  try {
    const sessions = await loadSessions();
    if (!sessions.length) {
      flashSave("暂无会话可导出");
      return;
    }

    const parts: string[] = ["# Herness 会话导出\n"];
    for (const session of sessions) {
      const messages = await loadMessages(session.id);
      parts.push(`## ${session.title}\n`);
      parts.push(`- persona: ${session.persona}`);
      parts.push(`- session_id: ${session.id}`);
      parts.push(`- user_id: ${session.userId}`);
      parts.push(`- updated: ${session.updatedAt}\n`);
      for (const msg of messages) {
        const role = msg.role === "user" ? "用户" : "助手";
        parts.push(`### ${role}\n\n${msg.content || "_(空)_"}\n`);
      }
      parts.push("\n---\n");
    }

    const blob = new Blob([parts.join("\n")], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `herness-export-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
    flashSave(`已导出 ${sessions.length} 个会话`);
  } finally {
    isExporting.value = false;
  }
}
</script>

<template>
  <AppShell
    theme="settings"
    title="Settings · 设置"
    subtitle="连接、身份、界面与本地数据"
    :show-trace="false"
    :show-sessions="false"
  >
    <div class="settings-page mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-8 md:flex-row md:gap-10 md:px-10 md:py-10">
      <nav
        class="settings-nav shrink-0 md:sticky md:top-8 md:w-44 md:self-start"
        aria-label="设置分区"
      >
        <p class="mb-3 hidden px-1 text-[10px] uppercase tracking-[0.14em] text-subtle md:block">
          分区
        </p>
        <div class="flex gap-2 overflow-x-auto pb-1 md:flex-col md:gap-1 md:overflow-visible md:pb-0">
          <button
            v-for="section in sections"
            :key="section.id"
            type="button"
            class="settings-nav-item shrink-0"
            :class="activeSection === section.id ? 'is-active' : ''"
            @click="scrollToSection(section.id)"
          >
            {{ section.label }}
          </button>
        </div>
      </nav>

      <div class="min-h-0 flex-1 space-y-8 overflow-y-auto pb-8">
        <div
          v-if="saveMessage"
          class="settings-flash animate-fade-up rounded-xl px-4 py-2.5 text-center text-xs theme-accent-text"
        >
          {{ saveMessage }}
        </div>

        <section id="settings-connection" class="settings-section glass-card p-6 md:p-8">
          <header class="settings-section-header">
            <div>
              <h2 class="text-[15px] font-normal text-zinc-100/90">连接与服务</h2>
              <p class="mt-1 text-xs text-subtle">配置后端 API 地址与鉴权密钥</p>
            </div>
            <HelpTip
              title="运行时覆盖"
              text="留空 API Key 表示开发模式无鉴权。修改后请点击保存并测试连接。"
            />
          </header>

          <div class="mt-6 space-y-5">
            <div>
              <label class="settings-label" for="api-base">API 地址</label>
              <input
                id="api-base"
                v-model="draftApiBase"
                class="theme-input mt-2 w-full px-4 py-3 font-mono text-sm text-zinc-300/90"
                placeholder="/api"
                spellcheck="false"
              />
              <p class="mt-2 text-[11px] text-subtle">
                解析为
                <code class="font-mono text-muted">{{ resolvedApiUrl }}</code>
                · 默认
                <code class="font-mono text-muted">{{ getDefaultApiBase() }}</code>
              </p>
            </div>

            <div>
              <div class="flex items-center justify-between">
                <label class="settings-label" for="api-key">API Key</label>
                <button
                  type="button"
                  class="text-[10px] text-subtle transition hover:theme-accent-text"
                  @click="showApiKey = !showApiKey"
                >
                  {{ showApiKey ? "隐藏" : "显示" }}
                </button>
              </div>
              <input
                id="api-key"
                v-model="draftApiKey"
                class="theme-input mt-2 w-full px-4 py-3 font-mono text-sm text-zinc-300/90"
                :type="showApiKey ? 'text' : 'password'"
                placeholder="留空 = 无鉴权"
                autocomplete="off"
                spellcheck="false"
              />
            </div>

            <div class="flex flex-wrap items-center gap-3 rounded-xl bg-white/[0.02] px-4 py-3">
              <span
                class="status-dot"
                :class="
                  settings.apiConnected === true
                    ? 'animate-pulse-glow'
                    : settings.apiConnected === false
                      ? '!bg-red-400/60 !opacity-100'
                      : '!opacity-30'
                "
              />
              <span class="text-xs text-muted">
                {{
                  settings.apiConnected === true
                    ? "在线"
                    : settings.apiConnected === false
                      ? "离线"
                      : "检测中"
                }}
              </span>
              <span class="text-[11px] text-subtle">· 最近检测 {{ lastCheckedLabel }}</span>
            </div>

            <p
              v-if="connectionMessage"
              class="text-center text-xs"
              :class="
                connectionMessage.type === 'success'
                  ? 'theme-accent-text'
                  : 'text-red-300/70'
              "
            >
              {{ connectionMessage.text }}
            </p>

            <div class="flex flex-wrap gap-3 pt-1">
              <button
                type="button"
                class="theme-btn-primary rounded-full px-5 py-2.5 text-[13px]"
                @click="saveConnection()"
              >
                保存连接
              </button>
              <button
                type="button"
                class="theme-btn-ghost px-5 py-2.5 text-[13px]"
                :disabled="isTestingConnection"
                @click="testConnection()"
              >
                {{ isTestingConnection ? "测试中…" : "测试连接" }}
              </button>
              <button
                type="button"
                class="theme-btn-ghost px-5 py-2.5 text-[13px]"
                @click="resetConnectionDraft()"
              >
                恢复默认
              </button>
            </div>
          </div>
        </section>

        <section id="settings-identity" class="settings-section glass-card p-6 md:p-8">
          <header class="settings-section-header">
            <div>
              <h2 class="text-[15px] font-normal text-zinc-100/90">身份与角色</h2>
              <p class="mt-1 text-xs text-subtle">C 端与 B 端 user_id，用于会话隔离与用量归因</p>
            </div>
          </header>

          <div class="mt-6 space-y-8">
            <div>
              <p class="settings-group-label">C 端 · 智能助手</p>
              <div class="mt-4 space-y-4">
                <div>
                  <label class="settings-label" for="consumer-id">用户 ID</label>
                  <input
                    id="consumer-id"
                    v-model="draftConsumerUserId"
                    class="theme-input mt-2 w-full px-4 py-3 font-mono text-sm text-zinc-300/90"
                    spellcheck="false"
                  />
                </div>
                <div class="settings-readonly-row">
                  <div class="min-w-0 flex-1">
                    <p class="settings-label">合成 user_id</p>
                    <p class="mt-1 truncate font-mono text-xs text-muted">
                      {{ consumerUserIdPreview }}
                    </p>
                  </div>
                  <button
                    type="button"
                    class="text-[10px] text-subtle transition hover:theme-accent-text"
                    @click="copyValue('consumer', consumerUserIdPreview)"
                  >
                    {{ copiedField === "consumer" ? "已复制" : "复制" }}
                  </button>
                </div>
                <p class="text-[11px] text-subtle">
                  Session 示例：
                  <code class="font-mono text-muted">{{ consumerSessionExample }}</code>
                </p>
                <div class="flex flex-wrap gap-3">
                  <button
                    type="button"
                    class="theme-btn-primary rounded-full px-5 py-2.5 text-[13px]"
                    @click="saveIdentity()"
                  >
                    保存身份
                  </button>
                  <button
                    type="button"
                    class="theme-btn-ghost px-5 py-2.5 text-[13px]"
                    @click="regenerateConsumerId()"
                  >
                    生成新 ID
                  </button>
                </div>
              </div>
            </div>

            <div class="border-t border-white/[0.04] pt-8">
              <p class="settings-group-label">B 端 · 商家运营</p>
              <div class="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <label class="settings-label" for="merchant-id">商家 ID</label>
                  <input
                    id="merchant-id"
                    v-model="draftMerchantId"
                    class="theme-input mt-2 w-full px-4 py-3 font-mono text-sm text-zinc-300/90"
                    spellcheck="false"
                  />
                </div>
                <div>
                  <label class="settings-label" for="operator-id">操作员 ID</label>
                  <input
                    id="operator-id"
                    v-model="draftOperatorId"
                    class="theme-input mt-2 w-full px-4 py-3 font-mono text-sm text-zinc-300/90"
                    spellcheck="false"
                  />
                </div>
              </div>
              <div class="settings-readonly-row mt-4">
                <div class="min-w-0 flex-1">
                  <p class="settings-label">合成 user_id</p>
                  <p class="mt-1 truncate font-mono text-xs text-muted">
                    {{ merchantUserIdPreview }}
                  </p>
                </div>
                <button
                  type="button"
                  class="text-[10px] text-subtle transition hover:theme-accent-text"
                  @click="copyValue('merchant', merchantUserIdPreview)"
                >
                  {{ copiedField === "merchant" ? "已复制" : "复制" }}
                </button>
              </div>
              <div class="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  class="theme-btn-primary rounded-full px-5 py-2.5 text-[13px]"
                  @click="saveIdentity()"
                >
                  保存身份
                </button>
                <button
                  type="button"
                  class="theme-btn-ghost px-5 py-2.5 text-[13px]"
                  @click="resetIdentityDraft()"
                >
                  恢复默认
                </button>
              </div>
            </div>
          </div>
        </section>

        <section id="settings-usage" class="settings-section glass-card p-6 md:p-8">
          <header class="settings-section-header">
            <div>
              <h2 class="text-[15px] font-normal text-zinc-100/90">用量与配额</h2>
              <p class="mt-1 text-xs text-subtle">
                用户与会话累计 token · 最近刷新 {{ usageLoadedLabel }}
              </p>
            </div>
            <HelpTip
              title="配额说明"
              text="配额上限由服务端 .env 配置。0 表示不限。达到 80% 时可在对话页显示预警。"
            />
          </header>

          <p v-if="usageError" class="mt-4 text-center text-xs text-red-300/70">
            {{ usageError }}
          </p>

          <div class="mt-6 grid gap-4 lg:grid-cols-2">
            <UsageQuotaCard
              label="C 端用户累计"
              :subtitle="consumerUserIdPreview"
              :usage="consumerUsage"
              :limit="userSessionLimit"
            />
            <UsageQuotaCard
              label="B 端用户累计"
              :subtitle="merchantUserIdPreview"
              :usage="merchantUsage"
              :limit="userSessionLimit"
            />
            <UsageQuotaCard
              v-if="chat.activeSessionId"
              class="lg:col-span-2"
              label="当前活跃会话"
              :subtitle="chat.activeSessionId"
              :usage="activeSessionUsage"
              :limit="sessionTokenLimit"
            />
          </div>

          <div class="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              class="theme-btn-primary rounded-full px-5 py-2.5 text-[13px]"
              :disabled="isRefreshingUsage"
              @click="refreshUsageStats()"
            >
              {{ isRefreshingUsage ? "刷新中…" : "刷新用量" }}
            </button>
          </div>
        </section>

        <section id="settings-interface" class="settings-section glass-card p-6 md:p-8">
          <header class="settings-section-header">
            <div>
              <h2 class="text-[15px] font-normal text-zinc-100/90">界面与体验</h2>
              <p class="mt-1 text-xs text-subtle">控制台布局与消息流偏好</p>
            </div>
          </header>

          <div class="mt-6 space-y-6 divide-y divide-white/[0.04]">
            <div class="pb-6">
              <SettingsToggle
                v-model="settings.tracePanelOpen"
                label="默认展开轨迹面板"
                description="桌面端进入对话页时是否显示 Agent 审计轨迹"
                @update:model-value="saveUiSettings()"
              />
            </div>
            <div class="py-6">
              <SettingsToggle
                v-model="settings.sidebarCollapsed"
                label="默认收起侧边栏"
                description="进入页面时侧边栏是否处于收起状态"
                @update:model-value="saveUiSettings()"
              />
            </div>
            <div class="py-6">
              <SettingsToggle
                v-model="settings.showTokenUsage"
                label="显示 Token 用量"
                description="在侧边栏与消息底部展示 token 统计"
                @update:model-value="saveUiSettings()"
              />
            </div>
            <div class="py-6">
              <SettingsToggle
                v-model="settings.autoScrollToBottom"
                label="自动滚动到底部"
                description="新消息到达时自动滚到对话底部"
                @update:model-value="saveUiSettings()"
              />
            </div>
            <div class="py-6">
              <SettingsToggle
                v-model="settings.showQuotaWarning"
                label="配额接近预警"
                description="用量达到 80% 时在对话输入框上方显示提示"
                @update:model-value="saveUiSettings()"
              />
            </div>
            <div class="pt-6">
              <p class="settings-label">消息流密度</p>
              <div class="mt-3 flex gap-2">
                <button
                  type="button"
                  class="settings-density-chip"
                  :class="settings.messageDensity === 'standard' ? 'is-active' : ''"
                  @click="
                    settings.messageDensity = 'standard';
                    saveUiSettings();
                  "
                >
                  标准
                </button>
                <button
                  type="button"
                  class="settings-density-chip"
                  :class="settings.messageDensity === 'compact' ? 'is-active' : ''"
                  @click="
                    settings.messageDensity = 'compact';
                    saveUiSettings();
                  "
                >
                  紧凑
                </button>
              </div>
            </div>
          </div>

          <div class="mt-8">
            <button
              type="button"
              class="theme-btn-ghost px-5 py-2.5 text-[13px]"
              @click="resetUiSettings()"
            >
              恢复界面默认
            </button>
          </div>
        </section>

        <section id="settings-data" class="settings-section glass-card p-6 md:p-8">
          <header class="settings-section-header">
            <div>
              <h2 class="text-[15px] font-normal text-zinc-100/90">数据与隐私</h2>
              <p class="mt-1 text-xs text-subtle">本地 IndexedDB 会话管理，不影响服务端数据</p>
            </div>
          </header>

          <div class="mt-6 space-y-4">
            <div class="settings-action-row">
              <div>
                <p class="text-[13px] text-zinc-200/90">导出全部会话</p>
                <p class="mt-1 text-xs text-subtle">合并导出为 Markdown 文件</p>
              </div>
              <button
                type="button"
                class="theme-btn-ghost shrink-0 px-4 py-2 text-[13px]"
                :disabled="isExporting"
                @click="exportAllSessions()"
              >
                {{ isExporting ? "导出中…" : "导出" }}
              </button>
            </div>

            <div class="settings-action-row">
              <div>
                <p class="text-[13px] text-zinc-200/90">清空 C 端对话</p>
                <p class="mt-1 text-xs text-subtle">删除智能助手全部本地会话</p>
              </div>
              <button
                type="button"
                class="settings-danger-btn shrink-0 px-4 py-2 text-[13px]"
                @click="clearConsumerSessions()"
              >
                清空
              </button>
            </div>

            <div class="settings-action-row">
              <div>
                <p class="text-[13px] text-zinc-200/90">清空 B 端对话</p>
                <p class="mt-1 text-xs text-subtle">删除商家运营全部本地会话</p>
              </div>
              <button
                type="button"
                class="settings-danger-btn shrink-0 px-4 py-2 text-[13px]"
                @click="clearMerchantSessions()"
              >
                清空
              </button>
            </div>
          </div>
        </section>

        <section id="settings-about" class="settings-section glass-card p-6 md:p-8">
          <header class="settings-section-header">
            <div>
              <h2 class="text-[15px] font-normal text-zinc-100/90">关于</h2>
              <p class="mt-1 text-xs text-subtle">Herness Agent Console</p>
            </div>
          </header>

          <dl class="mt-6 space-y-4 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="text-subtle">前端版本</dt>
              <dd class="font-mono text-muted">0.1.0</dd>
            </div>
            <div v-if="settings.publicConfig" class="flex justify-between gap-4">
              <dt class="text-subtle">LLM 模型</dt>
              <dd class="truncate font-mono text-xs text-muted">
                {{ settings.publicConfig.llm_model || "—" }}
              </dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-subtle">默认 API</dt>
              <dd class="truncate font-mono text-xs text-muted">{{ getDefaultApiBase() }}</dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-subtle">鉴权</dt>
              <dd class="text-muted">
                {{ getDefaultApiKey() ? "已配置默认 Key" : "开发模式（无 Key）" }}
              </dd>
            </div>
            <div v-if="settings.publicConfig" class="flex justify-between gap-4">
              <dt class="text-subtle">用户配额</dt>
              <dd class="font-mono text-xs text-muted">
                {{
                  userSessionLimit > 0
                    ? `${userSessionLimit.toLocaleString()} tokens`
                    : "不限"
                }}
              </dd>
            </div>
            <div v-if="settings.publicConfig" class="flex justify-between gap-4">
              <dt class="text-subtle">会话配额</dt>
              <dd class="font-mono text-xs text-muted">
                {{
                  sessionTokenLimit > 0
                    ? `${sessionTokenLimit.toLocaleString()} tokens`
                    : "不限"
                }}
              </dd>
            </div>
          </dl>

          <div v-if="featureLabels.length" class="mt-6 flex flex-wrap gap-2">
            <span
              v-for="item in featureLabels"
              :key="item.key"
              class="rounded-full px-2.5 py-1 text-[10px]"
              :class="
                item.enabled
                  ? 'theme-accent-bg theme-accent-text'
                  : 'bg-white/[0.03] text-subtle'
              "
            >
              {{ item.key }} {{ item.enabled ? "ON" : "OFF" }}
            </span>
          </div>

          <p class="mt-8 text-xs leading-relaxed text-subtle">
            服务端部署参数（模型、数据库、Rate Limit 等）请在
            <code class="font-mono text-muted">.env</code>
            中配置，前端仅展示连接状态。
          </p>

          <div class="mt-6 flex flex-wrap gap-3">
            <RouterLink to="/chat" class="theme-btn-ghost px-4 py-2 text-[13px]">
              返回智能助手
            </RouterLink>
            <RouterLink to="/ops" class="theme-btn-ghost px-4 py-2 text-[13px]">
              商家运营
            </RouterLink>
          </div>
        </section>
      </div>
    </div>
  </AppShell>
</template>
