import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { hernessApi } from "@/api/client";
import {
  getApiBase,
  getApiKey,
  getDefaultApiBase,
  getDefaultApiKey,
  resetApiConfig,
  setApiBase,
  setApiKey,
} from "@/lib/apiConfig";
import type { Persona, PersonaContext } from "@/types/herness";
import type { PublicConfigResponse } from "@/types/herness";
import {
  buildConsumerContext,
  buildMerchantContext,
} from "@/lib/persona";

export type MessageDensity = "standard" | "compact";

const UI_KEYS = {
  defaultTracePanelOpen: "herness:ui-trace-default",
  showTokenUsage: "herness:ui-show-token-usage",
  autoScrollToBottom: "herness:ui-auto-scroll",
  messageDensity: "herness:ui-message-density",
  sidebarCollapsed: "herness:ui-sidebar-collapsed",
  showQuotaWarning: "herness:ui-show-quota-warning",
} as const;

function readBool(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback;
  const raw = localStorage.getItem(key);
  if (raw === null) return fallback;
  return raw === "1";
}

function writeBool(key: string, value: boolean): void {
  localStorage.setItem(key, value ? "1" : "0");
}

function defaultTracePanelOpen(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(min-width: 768px)").matches;
}

function readMessageDensity(): MessageDensity {
  if (typeof window === "undefined") return "standard";
  const raw = localStorage.getItem(UI_KEYS.messageDensity);
  return raw === "compact" ? "compact" : "standard";
}

export const useSettingsStore = defineStore("settings", () => {
  const apiConnected = ref<boolean | null>(null);
  const apiLastCheckedAt = ref<string | null>(null);

  const apiBase = ref(getApiBase());
  const apiKey = ref(getApiKey());

  const tracePanelOpen = ref(
    readBool(UI_KEYS.defaultTracePanelOpen, defaultTracePanelOpen()),
  );
  const sidebarCollapsed = ref(readBool(UI_KEYS.sidebarCollapsed, false));
  const showTokenUsage = ref(readBool(UI_KEYS.showTokenUsage, true));
  const autoScrollToBottom = ref(readBool(UI_KEYS.autoScrollToBottom, true));
  const showQuotaWarning = ref(readBool(UI_KEYS.showQuotaWarning, true));
  const messageDensity = ref<MessageDensity>(readMessageDensity());
  const publicConfig = ref<PublicConfigResponse | null>(null);
  const publicConfigLoadedAt = ref<string | null>(null);

  const consumerUserId = ref(
    localStorage.getItem("herness:consumer-user-id") ??
      `guest-${crypto.randomUUID().slice(0, 8)}`,
  );

  const merchantId = ref(localStorage.getItem("herness:merchant-id") ?? "demo-shop");
  const operatorId = ref(localStorage.getItem("herness:operator-id") ?? "ops-001");

  watch(messageDensity, (value) => {
    localStorage.setItem(UI_KEYS.messageDensity, value);
    document.documentElement.dataset.messageDensity = value;
  }, { immediate: true });

  function getPersonaContext(persona: Persona): PersonaContext {
    if (persona === "merchant") {
      return buildMerchantContext(merchantId.value, operatorId.value);
    }
    return buildConsumerContext(consumerUserId.value);
  }

  function persistIdentity() {
    localStorage.setItem("herness:consumer-user-id", consumerUserId.value);
    localStorage.setItem("herness:merchant-id", merchantId.value);
    localStorage.setItem("herness:operator-id", operatorId.value);
  }

  function persistConnection() {
    setApiBase(apiBase.value);
    setApiKey(apiKey.value);
  }

  function persistUiSettings() {
    writeBool(UI_KEYS.defaultTracePanelOpen, tracePanelOpen.value);
    writeBool(UI_KEYS.sidebarCollapsed, sidebarCollapsed.value);
    writeBool(UI_KEYS.showTokenUsage, showTokenUsage.value);
    writeBool(UI_KEYS.autoScrollToBottom, autoScrollToBottom.value);
    writeBool(UI_KEYS.showQuotaWarning, showQuotaWarning.value);
    localStorage.setItem(UI_KEYS.messageDensity, messageDensity.value);
  }

  function resetConnectionSettings() {
    resetApiConfig();
    apiBase.value = getDefaultApiBase();
    apiKey.value = getDefaultApiKey();
  }

  function resetIdentitySettings() {
    consumerUserId.value = `guest-${crypto.randomUUID().slice(0, 8)}`;
    merchantId.value = "demo-shop";
    operatorId.value = "ops-001";
    persistIdentity();
  }

  function resetUiSettings() {
    tracePanelOpen.value = defaultTracePanelOpen();
    sidebarCollapsed.value = false;
    showTokenUsage.value = true;
    autoScrollToBottom.value = true;
    showQuotaWarning.value = true;
    messageDensity.value = "standard";
    persistUiSettings();
  }

  async function fetchPublicConfig(force = false): Promise<PublicConfigResponse | null> {
    if (publicConfig.value && !force) return publicConfig.value;
    try {
      publicConfig.value = await hernessApi.getPublicConfig();
      publicConfigLoadedAt.value = new Date().toISOString();
    } catch {
      publicConfig.value = null;
      publicConfigLoadedAt.value = null;
    }
    return publicConfig.value;
  }

  function regenerateConsumerUserId() {
    consumerUserId.value = `guest-${crypto.randomUUID().slice(0, 8)}`;
    persistIdentity();
  }

  function toggleTracePanel() {
    tracePanelOpen.value = !tracePanelOpen.value;
    writeBool(UI_KEYS.defaultTracePanelOpen, tracePanelOpen.value);
  }

  function closeTracePanel() {
    tracePanelOpen.value = false;
    writeBool(UI_KEYS.defaultTracePanelOpen, false);
  }

  function openTracePanel() {
    tracePanelOpen.value = true;
    writeBool(UI_KEYS.defaultTracePanelOpen, true);
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value;
    writeBool(UI_KEYS.sidebarCollapsed, sidebarCollapsed.value);
  }

  function markApiChecked(connected: boolean) {
    apiConnected.value = connected;
    apiLastCheckedAt.value = new Date().toISOString();
  }

  return {
    apiConnected,
    apiLastCheckedAt,
    apiBase,
    apiKey,
    tracePanelOpen,
    sidebarCollapsed,
    showTokenUsage,
    autoScrollToBottom,
    showQuotaWarning,
    messageDensity,
    publicConfig,
    publicConfigLoadedAt,
    consumerUserId,
    merchantId,
    operatorId,
    getPersonaContext,
    persistIdentity,
    persistConnection,
    persistUiSettings,
    resetConnectionSettings,
    resetIdentitySettings,
    resetUiSettings,
    regenerateConsumerUserId,
    fetchPublicConfig,
    toggleTracePanel,
    closeTracePanel,
    openTracePanel,
    toggleSidebar,
    markApiChecked,
  };
});
