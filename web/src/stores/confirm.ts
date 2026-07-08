import { defineStore } from "pinia";
import { ref } from "vue";

export type ConfirmTone = "default" | "danger";

export interface ConfirmOptions {
  title: string;
  message: string;
  detail?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
}

export const useConfirmStore = defineStore("confirm", () => {
  const open = ref(false);
  const options = ref<ConfirmOptions | null>(null);
  let resolver: ((value: boolean) => void) | null = null;

  function confirm(opts: ConfirmOptions): Promise<boolean> {
    if (open.value) {
      resolver?.(false);
    }
    return new Promise((resolve) => {
      options.value = {
        confirmLabel: "确定",
        cancelLabel: "取消",
        tone: "default",
        ...opts,
      };
      open.value = true;
      resolver = resolve;
    });
  }

  function accept() {
    open.value = false;
    options.value = null;
    resolver?.(true);
    resolver = null;
  }

  function dismiss() {
    open.value = false;
    options.value = null;
    resolver?.(false);
    resolver = null;
  }

  return { open, options, confirm, accept, dismiss };
});
