export type AppTheme = "consumer" | "merchant" | "rag" | "settings";

export const THEME_LABELS: Record<AppTheme, string> = {
  consumer: "C 端 · 薄荷绿",
  merchant: "B 端 · 淡紫",
  rag: "RAG · 暖黄",
  settings: "设置 · 中性灰",
};

export function themeAttr(theme: AppTheme): Record<string, AppTheme> {
  return { "data-theme": theme };
}
