import type { TaskMessage } from "@/types/herness";

export interface TraceProgress {
  progressText: string;
  content?: string;
}

const WORKER_TYPE_LABELS: Record<string, string> = {
  default: "通用任务",
  research: "信息检索",
  code: "代码执行",
  summary: "内容汇总",
  order_ops: "订单查询",
  product: "商品查询",
  traceability: "溯源查询",
};

/** 委派阶段左侧气泡用的进行时文案 */
const WORKER_PROGRESS_LABELS: Record<string, string> = {
  default: "正在执行任务",
  research: "正在检索资料",
  code: "正在执行代码",
  summary: "正在汇总内容",
  order_ops: "正在查询订单",
  product: "正在查询商品",
  traceability: "正在查询溯源信息",
};

function workerTypeLabel(type: string): string {
  return WORKER_TYPE_LABELS[type] ?? type;
}

function delegateProgressText(types: string[]): string {
  if (types.length === 1) {
    return WORKER_PROGRESS_LABELS[types[0]] ?? `正在执行：${workerTypeLabel(types[0])}`;
  }
  if (types.length > 1) {
    const labels = types.map(workerTypeLabel).join("、");
    return `正在执行：${labels}`;
  }
  return "正在规划任务";
}

/** 根据最新审计消息推导聊天气泡的进度文案与可预览内容。 */
export function progressFromTraceMessage(msg: TaskMessage): TraceProgress {
  const payload = msg.payload ?? {};

  switch (msg.role) {
    case "orchestrator": {
      if (msg.content.includes("已加载全局记忆")) {
        return { progressText: "正在理解你的问题" };
      }
      if (msg.content.includes("并行 Worker")) {
        return { progressText: "正在汇总结果" };
      }
      if (msg.content.includes("Critic 驳回")) {
        return { progressText: "结果待修正，重新处理中" };
      }
      if (msg.content.includes("重试")) {
        return { progressText: "网络波动，重试中" };
      }
      if (msg.content.includes("任务完成")) {
        return { progressText: "即将完成" };
      }
      if (msg.content.includes("Dreaming")) {
        return { progressText: "正在保存结果" };
      }
      return { progressText: "调度中" };
    }
    case "supervisor": {
      if (payload.action === "complete") {
        const answer =
          typeof payload.final_answer === "string" ? payload.final_answer.trim() : "";
        return {
          progressText: "正在生成回复",
          content: answer || undefined,
        };
      }
      if (payload.action === "delegate") {
        const types = Array.isArray(payload.worker_types)
          ? (payload.worker_types as string[])
          : [];
        return { progressText: delegateProgressText(types) };
      }
      if (payload.action === "abort") {
        return { progressText: "任务已中止" };
      }
      return { progressText: "正在分析需求" };
    }
    case "worker": {
      const invocations = Array.isArray(payload.tool_invocations)
        ? (payload.tool_invocations as Array<{ tool_name?: string }>)
        : [];
      const toolNames = invocations
        .map((item) => item.tool_name)
        .filter((name): name is string => Boolean(name));
      if (toolNames.length > 0) {
        const toolLabel =
          toolNames.length === 1
            ? toolNames[0]
            : toolNames.join("、");
        return { progressText: `正在调用 ${toolLabel}` };
      }
      const workerType =
        typeof payload.worker_type === "string" ? payload.worker_type : "";
      return {
        progressText: WORKER_PROGRESS_LABELS[workerType] ?? "正在整理结果",
      };
    }
    case "critic": {
      return {
        progressText: payload.passed ? "校验通过，汇总中" : "正在复核结果",
      };
    }
    default:
      return { progressText: "处理中" };
  }
}

export function answerFromTrace(trace: TaskMessage[]): string | undefined {
  for (let i = trace.length - 1; i >= 0; i -= 1) {
    const finalAnswer = trace[i].payload?.final_answer;
    if (typeof finalAnswer === "string" && finalAnswer.trim()) {
      return finalAnswer.trim();
    }
  }
  return undefined;
}
