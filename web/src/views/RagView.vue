<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { hernessApi } from "@/api/client";
import AppShell from "@/components/layout/AppShell.vue";
import KnowledgeGraph from "@/components/rag/KnowledgeGraph.vue";
import { useSettingsStore } from "@/stores/settings";
import type { RagGraphResponse, RagHit } from "@/types/herness";

const settings = useSettingsStore();

type Tab = "ingest" | "search" | "graph";

const activeTab = ref<Tab>("ingest");
const collectionId = ref("consumer");
const source = ref("console");
const ingestText = ref("");
const buildCommunities = ref(false);
const searchQuery = ref("");
const showCollectionHelp = ref(false);
const showSearchParams = ref(false);
const searchTopK = ref(20);
const searchMinScore = ref(0);
const useScoreFilter = ref(false);
const isDragging = ref(false);

const isIngesting = ref(false);
const isSearching = ref(false);
const isLoadingGraph = ref(false);
const isImportingSample = ref(false);
const ingestResult = ref<string | null>(null);
const toast = ref<{ type: "success" | "error"; message: string } | null>(null);
const searchResult = ref<{
  coarse_count: number;
  fine_count: number;
  hits: RagHit[];
} | null>(null);
const graphData = ref<RagGraphResponse | null>(null);
const selectedEntity = ref<string | null>(null);
const error = ref<string | null>(null);
const copiedChunkId = ref<number | null>(null);

const COLLECTIONS = [
  {
    id: "consumer",
    label: "Consumer · C 端",
    desc: "面向 C 端用户的商品、订单、溯源知识",
  },
  {
    id: "merchant",
    label: "Merchant · B 端",
    desc: "商家运营、库存、营收与售后知识",
  },
  {
    id: "default",
    label: "Default · 通用",
    desc: "跨场景共享的通用领域知识",
  },
];

const SAMPLE_DOC = `# GraphRAG 示例知识库

## 知识图谱（一键预览）
以下实体与关系专为图谱可视化设计，导入后即可看到连线。

洛川苹果是有机生鲜商品。
陕西洛川是洛川苹果的产地。
洛川苹果产自陕西洛川。

[洛川苹果] --产自--> [陕西洛川]
[订单A1024] --包含--> [洛川苹果]
[demo-shop商家] --销售--> [洛川苹果]
[订单A1024] --属于--> [demo-shop商家]

## 业务说明
消费者可在 App 查询订单A1024 的物流进度。
批次 B2024-88 的红富士苹果同样产自陕西洛川。
`;

onMounted(async () => {
  try {
    await hernessApi.healthCheck();
    settings.apiConnected = true;
  } catch {
    settings.apiConnected = false;
  }
  window.addEventListener("keydown", handleGlobalShortcut);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleGlobalShortcut);
});

function handleGlobalShortcut(e: KeyboardEvent) {
  if (activeTab.value !== "ingest") return;
  if (e.ctrlKey && e.key.toLowerCase() === "s") {
    e.preventDefault();
    void handleIngest();
  }
}

watch(collectionId, () => {
  graphData.value = null;
  selectedEntity.value = null;
});

watch(activeTab, (tab) => {
  if (tab === "graph" && !graphData.value && !isLoadingGraph.value) {
    void loadGraph();
  }
});

function showToast(type: "success" | "error", message: string) {
  toast.value = { type, message };
  window.setTimeout(() => {
    toast.value = null;
  }, 4000);
}

const filteredHits = () => {
  if (!searchResult.value) return [];
  if (!useScoreFilter.value) return searchResult.value.hits;
  return searchResult.value.hits.filter((h) => h.score >= searchMinScore.value);
};

async function handleIngest() {
  const text = ingestText.value.trim();
  if (!text || isIngesting.value) return;

  isIngesting.value = true;
  error.value = null;
  ingestResult.value = null;

  try {
    const res = await hernessApi.ragIngest({
      collection_id: collectionId.value,
      text,
      source: source.value.trim() || "console",
      build_communities: buildCommunities.value,
    });
    const msg = `已入库 ${res.chunk_ids.length} 个分块${
      res.communities_built > 0 ? `，生成 ${res.communities_built} 个社区摘要` : ""
    }`;
    ingestResult.value = msg;
    showToast("success", msg);
    ingestText.value = "";
    graphData.value = null;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "入库失败";
    error.value = msg;
    showToast("error", msg);
  } finally {
    isIngesting.value = false;
  }
}

async function handleSearch() {
  const query = searchQuery.value.trim();
  if (!query || isSearching.value) return;

  isSearching.value = true;
  error.value = null;
  searchResult.value = null;

  try {
    const res = await hernessApi.ragSearch({
      query,
      collection_id: collectionId.value,
    });
    searchResult.value = {
      coarse_count: res.coarse_count,
      fine_count: res.fine_count,
      hits: res.hits.slice(0, searchTopK.value),
    };
  } catch (err) {
    error.value = err instanceof Error ? err.message : "检索失败";
    showToast("error", error.value);
  } finally {
    isSearching.value = false;
  }
}

async function loadGraph() {
  isLoadingGraph.value = true;
  error.value = null;
  selectedEntity.value = null;

  try {
    graphData.value = await hernessApi.ragGraph(collectionId.value);
  } catch (err) {
    graphData.value = null;
    error.value = err instanceof Error ? err.message : "加载图谱失败";
    showToast("error", error.value);
  } finally {
    isLoadingGraph.value = false;
  }
}

async function importSampleData() {
  isImportingSample.value = true;
  ingestText.value = SAMPLE_DOC;
  source.value = "sample-graph";
  buildCommunities.value = true;
  activeTab.value = "ingest";
  await handleIngest();
  activeTab.value = "graph";
  await loadGraph();
  isImportingSample.value = false;
  if (graphData.value && graphData.value.edge_count > 0) {
    showToast(
      "success",
      `示例已导入：${graphData.value.entity_count} 实体 · ${graphData.value.edge_count} 关系`,
    );
  } else if (graphData.value) {
    showToast("error", "示例已入库但未抽取到关系，请确认 RAG 已启用后重试");
  }
}

function handleFiles(files: FileList | null) {
  if (!files?.length) return;
  const file = files[0];
  if (file.name.toLowerCase().endsWith(".pdf")) {
    showToast("error", "PDF 解析需后端支持，请使用 TXT/Markdown 或粘贴文本");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    ingestText.value = String(reader.result ?? "");
    showToast("success", `已加载文件：${file.name}`);
  };
  reader.readAsText(file);
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  isDragging.value = false;
  handleFiles(e.dataTransfer?.files ?? null);
}

function formatScore(score: number): string {
  return score.toFixed(3);
}

async function copyHit(content: string, chunkId: number) {
  await navigator.clipboard.writeText(content);
  copiedChunkId.value = chunkId;
  window.setTimeout(() => {
    if (copiedChunkId.value === chunkId) copiedChunkId.value = null;
  }, 1200);
}
</script>

<template>
  <AppShell
    theme="rag"
    title="RAG 知识库"
    subtitle="GraphRAG · 向量检索 · 文档入库"
    :show-trace="false"
    :show-sessions="false"
  >
    <div class="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <Transition
        enter-active-class="transition duration-300"
        enter-from-class="opacity-0 translate-y-1"
        leave-active-class="transition duration-200"
        leave-to-class="opacity-0"
      >
        <div
          v-if="toast"
          class="glass-card absolute right-8 top-6 z-30 max-w-xs px-4 py-3 text-[11px] font-normal"
          :class="toast.type === 'success' ? 'theme-accent-text' : 'text-red-300/70'"
        >
          {{ toast.message }}
        </div>
      </Transition>

      <div class="flex-1 overflow-y-auto px-6 py-8 md:px-12 md:py-10">
        <div
          class="mx-auto space-y-10"
          :class="activeTab === 'graph' ? 'max-w-6xl' : 'max-w-3xl'"
        >
          <!-- 集合切换 -->
          <section>
            <div class="mb-5 flex items-center justify-between">
              <p class="text-[11px] uppercase tracking-[0.14em] text-subtle">目标集合</p>
              <button
                type="button"
                class="text-[11px] text-subtle transition hover:text-muted"
                @click="showCollectionHelp = !showCollectionHelp"
              >
                {{ showCollectionHelp ? "收起" : "说明" }}
              </button>
            </div>
            <div class="inline-flex gap-1.5 rounded-2xl bg-white/[0.02] p-1.5">
              <button
                v-for="col in COLLECTIONS"
                :key="col.id"
                type="button"
                class="rounded-xl px-4 py-2.5 text-[13px] font-normal transition"
                :class="
                  collectionId === col.id
                    ? 'theme-accent-bg theme-accent-ring'
                    : 'text-muted hover:bg-white/[0.03]'
                "
                @click="collectionId = col.id"
              >
                {{ col.label }}
              </button>
            </div>
            <div
              v-if="showCollectionHelp"
              class="mt-5 space-y-2 text-[12px] leading-relaxed text-subtle"
            >
              <p v-for="col in COLLECTIONS" :key="col.id">
                {{ col.label }} — {{ col.desc }}
              </p>
            </div>
          </section>

          <!-- Tab -->
          <div class="inline-flex gap-1 rounded-2xl bg-white/[0.02] p-1.5">
            <button
              v-for="tab in [
                { id: 'ingest', label: '文档入库' },
                { id: 'search', label: '检索调试' },
                { id: 'graph', label: '知识图谱' },
              ]"
              :key="tab.id"
              type="button"
              class="rounded-xl px-5 py-2.5 text-[13px] font-normal transition"
              :class="
                activeTab === tab.id
                  ? 'theme-accent-bg theme-accent-ring'
                  : 'text-muted hover:bg-white/[0.03]'
              "
              @click="activeTab = tab.id as Tab"
            >
              {{ tab.label }}
            </button>
          </div>

          <p v-if="error" class="text-[12px] text-red-300/60">{{ error }}</p>

          <!-- 入库 -->
          <section v-if="activeTab === 'ingest'" class="space-y-8">
            <div class="glass-card px-6 py-5 md:px-8 md:py-6">
              <p class="text-[11px] uppercase tracking-[0.14em] text-subtle">来源标识</p>
              <input
                v-model="source"
                type="text"
                placeholder="console / manual / api"
                class="theme-input mt-4 w-full px-4 py-3.5 text-sm font-normal text-zinc-300/90 placeholder:text-subtle"
              />
              <p class="mt-3 text-[11px] text-subtle">标记文档来源，便于检索溯源</p>
            </div>

            <div class="glass-card px-6 py-5 md:px-8 md:py-6">
              <p class="text-[11px] uppercase tracking-[0.14em] text-subtle">文档内容</p>

              <div
                class="relative mt-6 rounded-2xl transition"
                :class="
                  isDragging
                    ? 'bg-white/[0.04]'
                    : 'bg-white/[0.015]'
                "
                style="box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04)"
                @dragover.prevent="isDragging = true"
                @dragleave="isDragging = false"
                @drop="onDrop"
              >
                <input
                  type="file"
                  accept=".txt,.md,.markdown"
                  class="absolute inset-0 cursor-pointer opacity-0"
                  @change="handleFiles(($event.target as HTMLInputElement).files)"
                />
                <div class="pointer-events-none px-6 py-16 text-center">
                  <p class="text-sm font-normal text-muted">拖拽 TXT / Markdown</p>
                  <p class="mt-2 text-[11px] text-subtle">或点击选择 · 也可下方粘贴</p>
                </div>
              </div>

              <textarea
                v-model="ingestText"
                rows="7"
                placeholder="粘贴文档文本…"
                class="theme-input mt-6 w-full resize-y px-4 py-4 text-sm font-normal leading-relaxed text-zinc-300/90 placeholder:text-subtle"
              />

              <label class="mt-8 flex cursor-pointer items-start gap-3">
                <input
                  v-model="buildCommunities"
                  type="checkbox"
                  class="mt-0.5 rounded opacity-60"
                />
                <span>
                  <span class="text-[13px] font-normal text-muted">构建 GraphRAG 社区摘要</span>
                  <span class="mt-1 block text-[11px] leading-relaxed text-subtle">
                    抽取实体关系并生成社区摘要，耗时较长
                  </span>
                </span>
              </label>
            </div>

            <div class="flex items-center gap-6">
              <button
                type="button"
                class="theme-btn-primary rounded-full px-6 py-3 text-[13px] font-normal"
                :disabled="!ingestText.trim() || isIngesting"
                @click="handleIngest"
              >
                {{ isIngesting ? "入库中…" : "提交入库" }}
              </button>
              <span class="text-[11px] text-subtle">Ctrl+S</span>
            </div>
          </section>

          <!-- 检索 -->
          <section v-else-if="activeTab === 'search'" class="space-y-8">
            <button
              type="button"
              class="text-[11px] text-subtle transition hover:text-muted"
              @click="showSearchParams = !showSearchParams"
            >
              {{ showSearchParams ? "收起参数" : "检索参数" }}
            </button>

            <div v-if="showSearchParams" class="glass-card grid gap-4 px-6 py-5 sm:grid-cols-3">
              <label class="text-[11px] text-subtle">
                top_k
                <input
                  v-model.number="searchTopK"
                  type="number"
                  min="1"
                  max="100"
                  class="theme-input mt-2 w-full px-3 py-2 text-sm"
                />
              </label>
              <label class="flex items-center gap-2 text-[11px] text-subtle sm:col-span-2">
                <input v-model="useScoreFilter" type="checkbox" class="rounded opacity-60" />
                相似度 ≥
                <input
                  v-model.number="searchMinScore"
                  type="number"
                  step="0.01"
                  class="theme-input w-20 px-2 py-1 text-sm"
                  :disabled="!useScoreFilter"
                />
              </label>
            </div>

            <div class="flex gap-3">
              <input
                v-model="searchQuery"
                type="text"
                placeholder="输入检索 query…"
                class="theme-input min-w-0 flex-1 px-5 py-4 text-sm font-normal placeholder:text-subtle"
                @keydown.enter="handleSearch"
              />
              <button
                type="button"
                class="theme-btn-primary shrink-0 rounded-full px-6 py-3 text-[13px] font-normal"
                :disabled="!searchQuery.trim() || isSearching"
                @click="handleSearch"
              >
                {{ isSearching ? "…" : "检索" }}
              </button>
            </div>

            <div v-if="searchResult" class="min-h-[240px] space-y-6 pt-4">
              <p class="text-[11px] text-subtle">
                粗 {{ searchResult.coarse_count }} · 细 {{ searchResult.fine_count }} · 展示
                {{ filteredHits().length }}
              </p>

              <p
                v-if="filteredHits().length === 0"
                class="py-20 text-center text-[13px] text-subtle"
              >
                未命中文档片段
              </p>

              <article
                v-for="hit in filteredHits()"
                :key="hit.chunk_id"
                class="glass-card px-6 py-5"
              >
                <div class="mb-4 flex flex-wrap items-center gap-3 text-[10px] text-subtle">
                  <span class="theme-accent-text opacity-70">{{ formatScore(hit.score) }}</span>
                  <span v-if="hit.retrieval_channel">{{ hit.retrieval_channel }}</span>
                  <span v-if="hit.source">{{ hit.source }}</span>
                  <button
                    type="button"
                    class="ml-auto hover:text-muted"
                    @click="copyHit(hit.content, hit.chunk_id)"
                  >
                    {{ copiedChunkId === hit.chunk_id ? "已复制" : "复制" }}
                  </button>
                </div>
                <p class="whitespace-pre-wrap text-[13px] font-normal leading-relaxed text-muted">
                  {{ hit.content }}
                </p>
              </article>
            </div>

            <div v-else class="min-h-[320px]" />
          </section>

          <!-- 图谱 -->
          <section v-else class="rag-graph-view">
            <header class="rag-graph-header">
              <div>
                <p class="rag-graph-eyebrow">GraphRAG</p>
                <h2 class="rag-graph-title">知识图谱可视化</h2>
                <p class="rag-graph-desc">
                  实体关系抽取 · hover 高亮完整链路
                  <span v-if="selectedEntity" class="theme-accent-text opacity-60">
                    · {{ selectedEntity }}
                  </span>
                </p>
              </div>
              <div class="rag-graph-actions">
                <button
                  type="button"
                  class="graph-action-btn"
                  :disabled="isLoadingGraph"
                  @click="loadGraph"
                >
                  {{ isLoadingGraph ? "抽取中…" : "刷新" }}
                </button>
                <button
                  type="button"
                  class="graph-action-btn"
                  :disabled="isImportingSample"
                  @click="importSampleData"
                >
                  {{ isImportingSample ? "导入中…" : "示例" }}
                </button>
              </div>
            </header>

            <div class="rag-graph-stage">
              <KnowledgeGraph
                :graph="graphData"
                :loading="isLoadingGraph"
                progress-hint="抽取实体与关系中…"
                @select-entity="selectedEntity = $event"
                @import-sample="importSampleData"
              />
            </div>

            <div v-if="graphData?.communities.length" class="rag-graph-communities">
              <div class="rag-graph-communities-head">
                <p class="text-[11px] uppercase tracking-[0.14em] text-subtle">社区摘要</p>
                <p class="text-[11px] text-subtle opacity-60">点击上方标签筛选子图</p>
              </div>
              <div class="rag-graph-communities-grid">
                <article
                  v-for="community in graphData.communities"
                  :key="community.community_id"
                  class="rag-community-card"
                >
                  <p class="mb-2.5 text-[10px] theme-accent-text opacity-55">
                    {{ community.community_id }}
                  </p>
                  <p class="text-[13px] font-normal leading-relaxed text-muted">
                    {{ community.summary }}
                  </p>
                </article>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </AppShell>
</template>
