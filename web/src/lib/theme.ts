export type AppTheme = "consumer" | "merchant" | "rag";

export const THEME_LABELS: Record<AppTheme, string> = {
  consumer: "C 端 · 薄荷绿",
  merchant: "B 端 · 淡紫",
  rag: "RAG · 暖黄",
};

export function themeAttr(theme: AppTheme): Record<string, AppTheme> {
  return { "data-theme": theme };
}
