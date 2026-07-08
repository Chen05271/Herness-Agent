import { defineStore } from "pinia";
import { ref } from "vue";
import type { Persona, PersonaContext } from "@/types/herness";
import {
  buildConsumerContext,
  buildMerchantContext,
} from "@/lib/persona";

function defaultTracePanelOpen(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(min-width: 768px)").matches;
}

export const useSettingsStore = defineStore("settings", () => {
  const apiConnected = ref<boolean | null>(null);
  const tracePanelOpen = ref(defaultTracePanelOpen());
  const sidebarCollapsed = ref(false);

  const consumerUserId = ref(
    localStorage.getItem("herness:consumer-user-id") ??
      `guest-${crypto.randomUUID().slice(0, 8)}`,
  );

  const merchantId = ref(localStorage.getItem("herness:merchant-id") ?? "demo-shop");
  const operatorId = ref(localStorage.getItem("herness:operator-id") ?? "ops-001");

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

  function toggleTracePanel() {
    tracePanelOpen.value = !tracePanelOpen.value;
  }

  function closeTracePanel() {
    tracePanelOpen.value = false;
  }

  function openTracePanel() {
    tracePanelOpen.value = true;
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  return {
    apiConnected,
    tracePanelOpen,
    sidebarCollapsed,
    consumerUserId,
    merchantId,
    operatorId,
    getPersonaContext,
    persistIdentity,
    toggleTracePanel,
    closeTracePanel,
    openTracePanel,
    toggleSidebar,
  };
});
