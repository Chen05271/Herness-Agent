const STORAGE_API_BASE = "herness:api-base";
const STORAGE_API_KEY = "herness:api-key";

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const DEFAULT_API_KEY = import.meta.env.VITE_API_KEY ?? "";

export function getApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  const stored = localStorage.getItem(STORAGE_API_BASE)?.trim();
  return stored || DEFAULT_API_BASE;
}

export function getApiKey(): string {
  if (typeof window === "undefined") return DEFAULT_API_KEY;
  const stored = localStorage.getItem(STORAGE_API_KEY);
  if (stored !== null) return stored;
  return DEFAULT_API_KEY;
}

export function getDefaultApiBase(): string {
  return DEFAULT_API_BASE;
}

export function getDefaultApiKey(): string {
  return DEFAULT_API_KEY;
}

export function setApiBase(value: string): void {
  const trimmed = value.trim();
  if (!trimmed || trimmed === DEFAULT_API_BASE) {
    localStorage.removeItem(STORAGE_API_BASE);
    return;
  }
  localStorage.setItem(STORAGE_API_BASE, trimmed);
}

export function setApiKey(value: string): void {
  if (value === DEFAULT_API_KEY) {
    localStorage.removeItem(STORAGE_API_KEY);
    return;
  }
  localStorage.setItem(STORAGE_API_KEY, value);
}

export function resetApiConfig(): void {
  localStorage.removeItem(STORAGE_API_BASE);
  localStorage.removeItem(STORAGE_API_KEY);
}

export function resolveApiUrl(base = getApiBase()): string {
  if (base.startsWith("http")) return base.replace(/\/$/, "");
  if (typeof window === "undefined") return base;
  return `${window.location.origin}${base}`.replace(/\/$/, "");
}
