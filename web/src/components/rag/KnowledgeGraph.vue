<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { RagGraphEntity, RagGraphResponse } from "@/types/herness";
import EmptyState from "@/components/ui/EmptyState.vue";
import HelpTip from "@/components/ui/HelpTip.vue";

const props = defineProps<{
  graph: RagGraphResponse | null;
  loading?: boolean;
  progressHint?: string;
}>();

const emit = defineEmits<{
  selectEntity: [name: string | null];
  importSample: [];
}>();

interface SimNode {
  id: string;
  name: string;
  entity_type: string;
  visual_type: string;
  chunk_ids: number[];
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface EntityStyle {
  label: string;
  hint: string;
  color: string;
  fill: string;
  radius: number;
  glow: string;
}

type RelationCategory = "ownership" | "sales" | "flow" | "trigger";

interface RelationStyle {
  category: RelationCategory;
  color: string;
  dash: string;
  badge: string;
  useGradient: boolean;
}

const ENTITY_STYLES: Record<string, EntityStyle> = {
  concept: {
    label: "概念",
    hint: "暖黄大节点 · 业务核心概念（商品、订单）",
    color: "#b89a62",
    fill: "rgba(184, 154, 98, 0.055)",
    radius: 26,
    glow: "rgba(184, 154, 98, 0.13)",
  },
  term: {
    label: "术语",
    hint: "薄荷绿中节点 · 业务术语（售后、物流）",
    color: "#62a888",
    fill: "rgba(98, 168, 136, 0.055)",
    radius: 17,
    glow: "rgba(98, 168, 136, 0.12)",
  },
  named: {
    label: "专名",
    hint: "淡紫小节点 · 专有名词（地名、商家 ID）",
    color: "#9a8ac4",
    fill: "rgba(154, 138, 196, 0.055)",
    radius: 11,
    glow: "rgba(154, 138, 196, 0.12)",
  },
};

const OWNERSHIP_KW = ["产自", "属于", "包含", "归属", "来自", "位于"];
const SALES_KW = ["销售", "销往"];
const FLOW_KW = ["流程", "状态", "待支付", "已发货", "物流", "支付", "配送"];
const TRIGGER_KW = ["触发", "预警", "规则", "超时", "通知"];

const CANVAS_INSET = 52;
const MAIN_H = 520;

const containerRef = ref<HTMLElement | null>(null);
const canvasWrapRef = ref<HTMLElement | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);
const selectedId = ref<string | null>(null);
const hoveredId = ref<string | null>(null);
const activeCommunityId = ref<string | null>(null);
const width = ref(720);
const height = ref(600);
const simNodes = ref<SimNode[]>([]);
const layoutFrame = ref(0);
const scale = ref(1);
const panX = ref(0);
const panY = ref(0);
const isPanning = ref(false);
const pointerDownOnSvg = ref(false);
const didDrag = ref(false);
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 });
const pointerOrigin = ref({ x: 0, y: 0 });
const DRAG_THRESHOLD = 4;
const typeFilter = ref<Record<string, boolean>>({
  named: true,
  term: true,
  concept: true,
});
const collapsedTypes = ref<Record<string, boolean>>({
  named: false,
  term: false,
  concept: false,
});
const showAllEntities = ref(false);

let frameId = 0;
let tickCount = 0;
let settleTicks = 0;
const MAX_TICKS = 320;
const MAX_SETTLE_TICKS = 80;

const edges = computed(() => props.graph?.edges ?? []);

const focusId = computed(() => selectedId.value ?? hoveredId.value);

let hoverRaf = 0;

const visibleNodes = computed(() =>
  simNodes.value.filter(
    (n) =>
      typeFilter.value[nodeVisualType(n)] !== false &&
      collapsedTypes.value[nodeVisualType(n)] !== true,
  ),
);

const nodeMap = computed(() => {
  const map = new Map<string, SimNode>();
  for (const node of simNodes.value) map.set(node.id, node);
  return map;
});

const entityCommunityMap = computed(() => {
  const map = new Map<string, string>();
  for (const community of props.graph?.communities ?? []) {
    for (const name of community.entity_names) {
      map.set(normalizeId(name), community.community_id);
    }
  }
  return map;
});

const highlightedIds = computed(() => {
  if (!focusId.value) return new Set<string>();
  const ids = new Set<string>([focusId.value]);
  for (const edge of edges.value) {
    const source = normalizeId(edge.source);
    const target = normalizeId(edge.target);
    if (source === focusId.value || target === focusId.value) {
      ids.add(source);
      ids.add(target);
    }
  }
  return ids;
});

const relationCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const edge of edges.value) {
    counts.set(edge.relation, (counts.get(edge.relation) ?? 0) + 1);
  }
  return counts;
});

const maxRelationCount = computed(() =>
  Math.max(1, ...Array.from(relationCounts.value.values())),
);

function classifyRelation(relation: string): RelationCategory {
  if (TRIGGER_KW.some((k) => relation.includes(k))) return "trigger";
  if (FLOW_KW.some((k) => relation.includes(k))) return "flow";
  if (SALES_KW.some((k) => relation.includes(k))) return "sales";
  if (OWNERSHIP_KW.some((k) => relation.includes(k))) return "ownership";
  if (relation === "related_to") return "ownership";
  return "ownership";
}

function relationStyle(relation: string): RelationStyle {
  const category = classifyRelation(relation);
  if (category === "flow") {
    return {
      category,
      color: "#62a888",
      dash: "5 4",
      badge: "流程",
      useGradient: true,
    };
  }
  if (category === "trigger") {
    return {
      category,
      color: "#9a8ac4",
      dash: "",
      badge: "触发",
      useGradient: false,
    };
  }
  if (category === "sales") {
    return {
      category,
      color: "#b89a62",
      dash: "3 3",
      badge: "销售",
      useGradient: false,
    };
  }
  return {
    category,
    color: "#b89a62",
    dash: "",
    badge: relation.includes("产自") ? "产自" : "归属",
    useGradient: false,
  };
}

function edgeLabel(relation: string): string {
  if (relation === "related_to") return relationStyle(relation).badge;
  return relation.length > 6 ? `${relation.slice(0, 6)}` : relation;
}

function edgeStrokeWidth(relation: string): number {
  const count = relationCounts.value.get(relation) ?? 1;
  return 0.6 + (count / maxRelationCount.value) * 1.2;
}

function entityStyle(type: string): EntityStyle {
  return ENTITY_STYLES[type] ?? ENTITY_STYLES.concept;
}

function nodeVisualType(node: SimNode): string {
  return node.visual_type in ENTITY_STYLES ? node.visual_type : node.entity_type;
}

function nodeRadius(node: SimNode, emphasized = false): number {
  const base = entityStyle(nodeVisualType(node)).radius;
  return emphasized ? base + 2.5 : base;
}

function normalizeId(name: string): string {
  return name.trim().toLowerCase();
}

function computeNodeDegrees(entityNames: string[]): Map<string, number> {
  const degrees = new Map<string, number>();
  for (const name of entityNames) degrees.set(normalizeId(name), 0);
  for (const edge of edges.value) {
    const src = normalizeId(edge.source);
    const tgt = normalizeId(edge.target);
    if (degrees.has(src)) degrees.set(src, (degrees.get(src) ?? 0) + 1);
    if (degrees.has(tgt)) degrees.set(tgt, (degrees.get(tgt) ?? 0) + 1);
  }
  return degrees;
}

function inferVisualType(entityType: string, degree: number, maxDegree: number): string {
  if (maxDegree >= 2 && degree === maxDegree) return "concept";
  if (degree >= 2) return "term";
  if (entityType === "named" || degree <= 1) return "named";
  return "term";
}

function selectLayoutEntities(allEntities: RagGraphEntity[]): RagGraphEntity[] {
  if (showAllEntities.value || allEntities.length <= 10) return allEntities;

  const linked = new Set<string>();
  for (const edge of edges.value) {
    linked.add(normalizeId(edge.source));
    linked.add(normalizeId(edge.target));
  }

  const connected = allEntities.filter((entity) => linked.has(normalizeId(entity.name)));
  if (connected.length >= 2) return connected;

  return allEntities.filter(
    (entity) => entity.entity_type !== "term" || linked.has(normalizeId(entity.name)),
  );
}

const layoutEntityCount = computed(() => {
  if (!props.graph) return 0;
  return selectLayoutEntities(props.graph.entities).length;
});

const hiddenEntityCount = computed(() => {
  if (!props.graph || showAllEntities.value) return 0;
  return Math.max(0, props.graph.entities.length - layoutEntityCount.value);
});

function minNodeDistance(a: SimNode, b: SimNode): number {
  return nodeRadius(a) + nodeRadius(b) + 36;
}

function resolveCollisions(nodes: SimNode[], strength = 1): void {
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i];
      const b = nodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let dist = Math.hypot(dx, dy) || 0.001;
      const minDist = minNodeDistance(a, b);
      if (dist >= minDist) continue;
      const push = ((minDist - dist) / 2) * strength;
      dx /= dist;
      dy /= dist;
      a.x -= dx * push;
      a.y -= dy * push;
      b.x += dx * push;
      b.y += dy * push;
    }
  }
}

function layoutInitialCluster(
  type: string,
  list: RagGraphEntity[],
  degrees: Map<string, number>,
  maxDegree: number,
): SimNode[] {
  const center = clusterCenter(type);
  const minGap = 64;
  const count = list.length;
  const ring = Math.max(minGap * 0.85, (minGap * count) / (2 * Math.PI));
  const spread = count > 1 ? Math.min(Math.PI * 1.45, (count / 6) * Math.PI * 1.2) : 0;

  return list.map((entity, index) => {
    const id = normalizeId(entity.name);
    const degree = degrees.get(id) ?? 0;
    const angle =
      count === 1
        ? -Math.PI / 2
        : -Math.PI / 2 - spread / 2 + (spread * index) / Math.max(count - 1, 1);
    return {
      id,
      name: entity.name,
      entity_type: entity.entity_type,
      visual_type: inferVisualType(entity.entity_type, degree, maxDegree),
      chunk_ids: entity.chunk_ids,
      x: center.x + ring * Math.cos(angle),
      y: center.y + ring * Math.sin(angle),
      vx: 0,
      vy: 0,
    };
  });
}

function resolveNode(name: string): SimNode | null {
  const key = normalizeId(name);
  const exact = nodeMap.value.get(key);
  if (exact) return exact;

  let best: SimNode | null = null;
  let bestScore = 0;
  for (const node of simNodes.value) {
    if (node.id === key || node.name.toLowerCase() === key) return node;
    if (node.id.includes(key) || key.includes(node.id)) {
      const score = Math.min(node.id.length, key.length);
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
  }
  return best;
}

function nodeInActiveCommunity(node: SimNode): boolean {
  if (!activeCommunityId.value) return true;
  return entityCommunityMap.value.get(node.id) === activeCommunityId.value;
}

interface DrawableEdge {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  mx: number;
  my: number;
  relation: string;
  label: string;
  source: string;
  target: string;
  style: RelationStyle;
  strokeWidth: number;
  highlighted: boolean;
  zOrder: number;
}

const drawableEdges = computed<DrawableEdge[]>(() => {
  void layoutFrame.value;
  const result: DrawableEdge[] = [];

  for (const [index, edge] of edges.value.entries()) {
    const source = resolveNode(edge.source);
    const target = resolveNode(edge.target);
    if (!source || !target) continue;
    if (typeFilter.value[nodeVisualType(source)] === false) continue;
    if (typeFilter.value[nodeVisualType(target)] === false) continue;
    if (collapsedTypes.value[nodeVisualType(source)]) continue;
    if (collapsedTypes.value[nodeVisualType(target)]) continue;
    if (activeCommunityId.value) {
      const srcOk = entityCommunityMap.value.get(source.id) === activeCommunityId.value;
      const tgtOk = entityCommunityMap.value.get(target.id) === activeCommunityId.value;
      if (!srcOk && !tgtOk) continue;
    }

    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dist = Math.hypot(dx, dy) || 1;
    const padS = nodeRadius(source) + 5;
    const padT = nodeRadius(target) + 5;
    const x1 = source.x + (dx / dist) * padS;
    const y1 = source.y + (dy / dist) * padS;
    const x2 = target.x - (dx / dist) * padT;
    const y2 = target.y - (dy / dist) * padT;

    const srcId = normalizeId(edge.source);
    const tgtId = normalizeId(edge.target);
    const highlighted =
      !focusId.value ||
      (highlightedIds.value.has(srcId) && highlightedIds.value.has(tgtId));

    result.push({
      key: `${edge.source}-${edge.target}-${edge.relation}-${index}`,
      x1,
      y1,
      x2,
      y2,
      mx: (x1 + x2) / 2,
      my: (y1 + y2) / 2,
      relation: edge.relation,
      label: edgeLabel(edge.relation),
      source: edge.source,
      target: edge.target,
      style: relationStyle(edge.relation),
      strokeWidth: edgeStrokeWidth(edge.relation),
      highlighted,
      zOrder: index,
    });
  }

  return result;
});

interface ClusterBounds {
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  count: number;
  label: string;
  cx: number;
  cy: number;
}

const clusterBounds = computed<ClusterBounds[]>(() => {
  void layoutFrame.value;
  const bounds: ClusterBounds[] = [];

  for (const type of ["concept", "term", "named"]) {
    if (collapsedTypes.value[type]) continue;
    const nodes = simNodes.value.filter(
      (n) => nodeVisualType(n) === type && typeFilter.value[type] !== false,
    );
    if (!nodes.length) continue;

    const pad = 52;
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs) - pad;
    const maxX = Math.max(...xs) + pad;
    const minY = Math.min(...ys) - pad;
    const maxY = Math.max(...ys) + pad;

    bounds.push({
      type,
      x: minX,
      y: minY,
      width: maxX - minX,
      height: maxY - minY,
      count: nodes.length,
      label: ENTITY_STYLES[type].label,
      cx: (minX + maxX) / 2,
      cy: minY - 6,
    });
  }
  return bounds;
});

const matchedEdgeCount = computed(() => drawableEdges.value.length);

function clusterCenter(type: string): { x: number; y: number } {
  const w = width.value;
  const h = MAIN_H;
  if (type === "concept") return { x: w * 0.5, y: h * 0.36 };
  if (type === "term") return { x: w * 0.27, y: h * 0.64 };
  if (type === "named") return { x: w * 0.73, y: h * 0.64 };
  return { x: w * 0.5, y: h * 0.5 };
}

function measureContainer() {
  const el = canvasWrapRef.value ?? containerRef.value;
  if (!el) return 0;
  const nextWidth = Math.max(el.clientWidth - CANVAS_INSET * 2, 320);
  width.value = nextWidth;
  return nextWidth;
}

function relayoutOnResize() {
  if (!simNodes.value.length) return;
  for (const node of simNodes.value) {
    const center = clusterCenter(nodeVisualType(node));
    node.x = center.x + (node.x - center.x) * 0.9;
    node.y = center.y + (node.y - center.y) * 0.9;
  }
  for (let i = 0; i < 24; i += 1) resolveCollisions(simNodes.value, 0.85);
  layoutFrame.value += 1;
}

function stopSimulation() {
  if (frameId) {
    cancelAnimationFrame(frameId);
    frameId = 0;
  }
}

function initSimulation() {
  stopSimulation();
  tickCount = 0;
  settleTicks = 0;
  selectedId.value = null;
  hoveredId.value = null;
  activeCommunityId.value = null;
  emit("selectEntity", null);
  scale.value = 1;
  panX.value = 0;
  panY.value = 0;
  collapsedTypes.value = { named: false, term: false, concept: false };

  const allEntities = props.graph?.entities ?? [];
  if (allEntities.length === 0) {
    simNodes.value = [];
    return;
  }

  const entities = selectLayoutEntities(allEntities);
  const degrees = computeNodeDegrees(entities.map((entity) => entity.name));
  const maxDegree = Math.max(1, ...Array.from(degrees.values()));

  const grouped: Record<string, RagGraphEntity[]> = {
    concept: [],
    term: [],
    named: [],
  };
  for (const entity of entities) {
    const id = normalizeId(entity.name);
    const degree = degrees.get(id) ?? 0;
    const visualType = inferVisualType(entity.entity_type, degree, maxDegree);
    grouped[visualType].push(entity);
  }

  const nodes: SimNode[] = [];
  for (const [type, list] of Object.entries(grouped)) {
    nodes.push(...layoutInitialCluster(type, list, degrees, maxDegree));
  }

  simNodes.value = nodes;
  tickCount = 0;
  settleTicks = 0;
  frameId = requestAnimationFrame(tick);
}

function tick() {
  const nodes = simNodes.value;
  const inset = CANVAS_INSET + 24;
  const isSettling = tickCount >= MAX_TICKS;
  const alpha = isSettling
    ? Math.max(0, 1 - settleTicks / MAX_SETTLE_TICKS)
    : Math.max(0, 1 - tickCount / MAX_TICKS);
  const cx = width.value / 2;
  const cy = MAIN_H / 2;

  if (!isSettling) {
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy) || 1;
        const crossCluster = nodeVisualType(a) !== nodeVisualType(b) ? 2.2 : 1;
        const repulse = ((18000 * crossCluster) * alpha) / (dist * dist);
        dx /= dist;
        dy /= dist;
        a.vx -= dx * repulse;
        a.vy -= dy * repulse;
        b.vx += dx * repulse;
        b.vy += dy * repulse;
      }
    }

    for (const edge of edges.value) {
      const source = nodeMap.value.get(normalizeId(edge.source));
      const target = nodeMap.value.get(normalizeId(edge.target));
      if (!source || !target) continue;
      let dx = target.x - source.x;
      let dy = target.y - source.y;
      const dist = Math.hypot(dx, dy) || 1;
      const ideal = minNodeDistance(source, target) * 1.75;
      const force = (dist - ideal) * 0.028 * alpha;
      dx /= dist;
      dy /= dist;
      source.vx += dx * force;
      source.vy += dy * force;
      target.vx -= dx * force;
      target.vy -= dy * force;
    }

    for (const node of nodes) {
      const cluster = clusterCenter(nodeVisualType(node));
      node.vx += (cluster.x - node.x) * 0.008 * alpha;
      node.vy += (cluster.y - node.y) * 0.008 * alpha;
      node.vx += (cx - node.x) * 0.0025 * alpha;
      node.vy += (cy - node.y) * 0.0025 * alpha;
      node.vx *= 0.84;
      node.vy *= 0.84;
      node.x += node.vx;
      node.y += node.vy;
    }
  }

  resolveCollisions(nodes, isSettling ? 0.85 : 0.55);

  for (const node of nodes) {
    node.x = Math.max(inset, Math.min(width.value - inset, node.x));
    node.y = Math.max(inset, Math.min(MAIN_H - inset, node.y));
  }

  tickCount += 1;
  layoutFrame.value += 1;

  if (tickCount < MAX_TICKS) {
    frameId = requestAnimationFrame(tick);
    return;
  }

  settleTicks += 1;
  if (settleTicks < MAX_SETTLE_TICKS) {
    frameId = requestAnimationFrame(tick);
  } else {
    frameId = 0;
    layoutFrame.value += 1;
  }
}

function clientToGraph(clientX: number, clientY: number): { x: number; y: number } {
  const svg = svgRef.value;
  if (!svg) return { x: 0, y: 0 };
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const inverse = svg.getScreenCTM()?.inverse();
  if (!inverse) return { x: 0, y: 0 };
  const svgPoint = pt.matrixTransform(inverse);
  return {
    x: (svgPoint.x - panX.value) / scale.value,
    y: (svgPoint.y - panY.value) / scale.value,
  };
}

function findNodeAt(x: number, y: number): SimNode | null {
  let hit: SimNode | null = null;
  let bestDist = Infinity;
  for (const node of visibleNodes.value) {
    const radius = nodeRadius(node) + 18;
    const dist = Math.hypot(node.x - x, node.y - y);
    if (dist <= radius && dist < bestDist) {
      bestDist = dist;
      hit = node;
    }
  }
  return hit;
}

function scheduleHoverPick(clientX: number, clientY: number) {
  if (isPanning.value) return;
  if (hoverRaf) cancelAnimationFrame(hoverRaf);
  hoverRaf = requestAnimationFrame(() => {
    hoverRaf = 0;
    const point = clientToGraph(clientX, clientY);
    const node = findNodeAt(point.x, point.y);
    const nextId = node?.id ?? null;
    if (hoveredId.value !== nextId) hoveredId.value = nextId;
  });
}

function handleNodeClick(node: SimNode) {
  selectedId.value = selectedId.value === node.id ? null : node.id;
  emit("selectEntity", selectedId.value ? node.name : null);
}

function clearHover() {
  if (hoverRaf) {
    cancelAnimationFrame(hoverRaf);
    hoverRaf = 0;
  }
  hoveredId.value = null;
}

function onSvgPointerLeave() {
  if (!isPanning.value) clearHover();
}

function onSvgClick(e: PointerEvent) {
  if (didDrag.value) {
    didDrag.value = false;
    return;
  }
  const point = clientToGraph(e.clientX, e.clientY);
  const node = findNodeAt(point.x, point.y);
  if (node) {
    handleNodeClick(node);
    return;
  }
  handleCanvasClick();
}

function edgeOpacity(edge: DrawableEdge): number {
  if (!focusId.value) return 0.44;
  return edge.highlighted ? 0.9 : 0.14;
}

function handleCanvasClick() {
  selectedId.value = null;
  emit("selectEntity", null);
}

function nodeVisualOpacity(node: SimNode): number {
  const vtype = nodeVisualType(node);
  if (collapsedTypes.value[vtype]) return 0;
  if (typeFilter.value[vtype] === false) return 0;
  if (activeCommunityId.value && !nodeInActiveCommunity(node)) return 0.2;
  if (!focusId.value) return 1;
  return highlightedIds.value.has(node.id) ? 1 : 0.15;
}

function labelOpacity(node: SimNode): number {
  const emphasized = selectedId.value === node.id;
  const hovered = hoveredId.value === node.id;
  if (emphasized || hovered) return 0.88;
  if (!focusId.value) return 0.38;
  return highlightedIds.value.has(node.id) ? 0.72 : 0.16;
}

function labelSize(node: SimNode): number {
  const emphasized = selectedId.value === node.id;
  return emphasized ? 10 : 8;
}

function toggleShowAllEntities() {
  showAllEntities.value = !showAllEntities.value;
  initSimulation();
}

function toggleCommunity(communityId: string) {
  activeCommunityId.value =
    activeCommunityId.value === communityId ? null : communityId;
}

function zoom(delta: number) {
  scale.value = Math.min(2.2, Math.max(0.55, scale.value + delta));
}

function resetView() {
  scale.value = 1;
  panX.value = 0;
  panY.value = 0;
  selectedId.value = null;
  activeCommunityId.value = null;
  typeFilter.value = { named: true, term: true, concept: true };
  collapsedTypes.value = { named: false, term: false, concept: false };
  emit("selectEntity", null);
}

function onWheel(e: WheelEvent) {
  e.preventDefault();
  zoom(e.deltaY > 0 ? -0.06 : 0.06);
}

function onPointerDown(e: PointerEvent) {
  pointerDownOnSvg.value = true;
  didDrag.value = false;
  isPanning.value = false;
  pointerOrigin.value = { x: e.clientX, y: e.clientY };
  panStart.value = { x: e.clientX, y: e.clientY, panX: panX.value, panY: panY.value };
  clearHover();
  (e.currentTarget as Element).setPointerCapture(e.pointerId);
}

function onSvgPointerEnter(e: PointerEvent) {
  if (!pointerDownOnSvg.value) scheduleHoverPick(e.clientX, e.clientY);
}

function onPointerMove(e: PointerEvent) {
  if (!pointerDownOnSvg.value) {
    scheduleHoverPick(e.clientX, e.clientY);
    return;
  }

  if (!didDrag.value) {
    const dx = e.clientX - pointerOrigin.value.x;
    const dy = e.clientY - pointerOrigin.value.y;
    if (Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
      didDrag.value = true;
      isPanning.value = true;
    }
  }
  if (isPanning.value) {
    panX.value = panStart.value.panX + (e.clientX - panStart.value.x);
    panY.value = panStart.value.panY + (e.clientY - panStart.value.y);
    return;
  }
  scheduleHoverPick(e.clientX, e.clientY);
}

function onPointerUp(e: PointerEvent) {
  pointerDownOnSvg.value = false;
  isPanning.value = false;
  (e.currentTarget as Element).releasePointerCapture(e.pointerId);
}

function exportSvg() {
  if (!svgRef.value) return;
  const blob = new Blob([svgRef.value.outerHTML], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `herness-graph-${Date.now()}.svg`;
  a.click();
  URL.revokeObjectURL(url);
}

let resizeObserver: ResizeObserver | null = null;
let resizeTimer: ReturnType<typeof setTimeout> | null = null;
let lastCanvasWidth = 0;

function handleCanvasResize() {
  const nextWidth = measureContainer();
  if (Math.abs(nextWidth - lastCanvasWidth) < 2) return;
  lastCanvasWidth = nextWidth;
  relayoutOnResize();
}

onMounted(() => {
  lastCanvasWidth = measureContainer();
  resizeObserver = new ResizeObserver(() => {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(handleCanvasResize, 120);
  });
  if (canvasWrapRef.value) resizeObserver.observe(canvasWrapRef.value);
  initSimulation();
});

onUnmounted(() => {
  stopSimulation();
  if (hoverRaf) cancelAnimationFrame(hoverRaf);
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeObserver?.disconnect();
});

watch(
  () => props.graph,
  () => {
    showAllEntities.value = false;
    lastCanvasWidth = measureContainer();
    initSimulation();
  },
  { deep: true },
);
</script>

<template>
  <div ref="containerRef" class="relative w-full">
    <div
      v-if="loading"
      class="mb-6 flex items-center gap-3 px-2 py-2 text-[11px] font-normal text-muted"
    >
      <span class="status-dot animate-pulse-glow" />
      {{ progressHint ?? "正在抽取实体与关系…" }}
    </div>

    <div v-if="!graph || graph.entities.length === 0" class="glass-card overflow-hidden">
      <EmptyState
        icon="graph"
        title="暂无图谱"
        description="完成文档入库后，GraphRAG 将自动抽取实体与关系。"
      >
        <template #actions>
          <button
            type="button"
            class="theme-btn-primary rounded-full px-5 py-2.5 text-[12px] font-normal"
            @click="emit('importSample')"
          >
            导入示例
          </button>
        </template>
      </EmptyState>
    </div>

    <div v-else class="graph-canvas-card overflow-hidden">
      <!-- 顶部工具栏：图例左 · 操作右 -->
      <div class="graph-toolbar">
        <div class="graph-toolbar-legend">
          <label
            v-for="(style, type) in ENTITY_STYLES"
            :key="type"
            class="graph-legend-item group"
            :title="style.hint"
          >
            <input
              v-model="typeFilter[type]"
              type="checkbox"
              class="sr-only"
            />
            <span
              class="graph-legend-dot"
              :class="{ 'graph-legend-dot--off': !typeFilter[type] }"
              :style="{ '--dot-color': style.color }"
            />
            <span class="graph-legend-text">{{ style.label }}</span>
            <span class="graph-legend-tip">{{ style.hint }}</span>
          </label>
        </div>

        <div class="graph-toolbar-actions">
          <HelpTip
            title="图谱交互"
            text="拖拽空白区域平移画布；滚轮缩放；单击节点聚焦关联链路；双击聚类框折叠子图；点击社区标签筛选子图。"
          />
          <button type="button" class="graph-toolbar-btn graph-toolbar-btn--icon" title="放大" @click="zoom(0.12)">+</button>
          <button type="button" class="graph-toolbar-btn graph-toolbar-btn--icon" title="缩小" @click="zoom(-0.12)">−</button>
          <button type="button" class="graph-toolbar-btn graph-toolbar-btn--icon" title="重置视图" @click="resetView">↺</button>
          <button type="button" class="graph-toolbar-btn" title="导出 SVG" @click="exportSvg">SVG</button>
        </div>
      </div>

      <!-- 画布区 -->
      <div ref="canvasWrapRef" class="graph-canvas-wrap">
        <svg
          ref="svgRef"
          :viewBox="`0 0 ${width} ${height}`"
          class="graph-svg"
          :class="{ 'graph-svg--hoverable': !isPanning }"
          role="img"
          aria-label="GraphRAG 知识图谱"
          @wheel="onWheel"
          @pointerdown="onPointerDown"
          @pointerenter="onSvgPointerEnter"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointerleave="onSvgPointerLeave"
          @click="onSvgClick"
        >
          <defs>
            <pattern id="graph-grid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path
                d="M 48 0 L 0 0 0 48"
                fill="none"
                stroke="rgba(255,255,255,0.02)"
                stroke-width="0.5"
              />
            </pattern>

            <linearGradient id="flow-edge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="#62a888" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#62a888" stop-opacity="0.62" />
            </linearGradient>
          </defs>

          <rect
            :x="CANVAS_INSET"
            :y="CANVAS_INSET"
            :width="width - CANVAS_INSET * 2"
            :height="MAIN_H - CANVAS_INSET"
            rx="20"
            fill="url(#graph-grid)"
          />
          <rect
            :x="CANVAS_INSET"
            :y="CANVAS_INSET"
            :width="width - CANVAS_INSET * 2"
            :height="MAIN_H - CANVAS_INSET"
            rx="20"
            fill="rgba(255,255,255,0.006)"
          />

          <g :transform="`translate(${panX} ${panY}) scale(${scale})`">
            <!-- 聚类虚线框（不遮挡） -->
            <g
              v-for="cluster in clusterBounds"
              :key="`cluster-${cluster.type}`"
              class="graph-cluster"
              pointer-events="none"
            >
              <rect
                :x="cluster.x"
                :y="cluster.y"
                :width="cluster.width"
                :height="cluster.height"
                rx="24"
                fill="none"
                :stroke="ENTITY_STYLES[cluster.type].color"
                stroke-opacity="0.07"
                stroke-width="0.75"
                stroke-dasharray="8 7"
              />
            </g>

            <!-- 关系连线（底层遮罩 + 分色 + 标签） -->
            <g v-for="edge in drawableEdges" :key="edge.key" pointer-events="none">
              <!-- 交叉处分层遮罩 -->
              <line
                :x1="edge.x1"
                :y1="edge.y1"
                :x2="edge.x2"
                :y2="edge.y2"
                stroke="rgba(8,8,10,0.85)"
                :stroke-width="edge.strokeWidth + 2.5"
                stroke-linecap="round"
                :opacity="edgeOpacity(edge) * 0.55"
              />
              <line
                :x1="edge.x1"
                :y1="edge.y1"
                :x2="edge.x2"
                :y2="edge.y2"
                :stroke="edge.style.useGradient ? 'url(#flow-edge-gradient)' : edge.style.color"
                :stroke-width="edge.strokeWidth"
                :stroke-dasharray="edge.style.dash || undefined"
                stroke-linecap="round"
                :opacity="edgeOpacity(edge)"
              />
              <rect
                :x="edge.mx - (edge.label.length * 3.4 + 12)"
                :y="edge.my - 8"
                :width="edge.label.length * 6.8 + 24"
                height="16"
                rx="8"
                fill="rgba(6,6,8,0.42)"
                :opacity="edgeOpacity(edge) * (edge.highlighted ? 0.92 : 0.55)"
              />
              <text
                :x="edge.mx"
                :y="edge.my + 3"
                text-anchor="middle"
                :fill="edge.style.color"
                :fill-opacity="edge.highlighted ? 0.78 : 0.34"
                class="select-none font-normal tracking-wide"
                :style="{ fontSize: `${edge.highlighted ? 9 : 8}px` }"
                :opacity="edgeOpacity(edge)"
              >
                {{ edge.label }}
              </text>
            </g>

            <!-- 实体节点 -->
            <g
              v-for="node in visibleNodes"
              :key="node.id"
              class="graph-node"
              pointer-events="none"
            >
              <circle
                :cx="node.x"
                :cy="node.y"
                :r="nodeRadius(node, selectedId === node.id) + 10"
                :fill="entityStyle(nodeVisualType(node)).glow"
                :opacity="(hoveredId === node.id || selectedId === node.id ? 0.22 : 0) * nodeVisualOpacity(node)"
              />
              <circle
                :cx="node.x"
                :cy="node.y"
                :r="nodeRadius(node, selectedId === node.id)"
                :fill="entityStyle(nodeVisualType(node)).fill"
                :stroke="entityStyle(nodeVisualType(node)).color"
                stroke-opacity="0.38"
                stroke-width="0.75"
                :opacity="nodeVisualOpacity(node)"
              />
              <circle
                :cx="node.x"
                :cy="node.y"
                :r="nodeRadius(node) - 5"
                fill="rgba(255,255,255,0.028)"
                :opacity="nodeVisualOpacity(node)"
              />
              <text
                :x="node.x"
                :y="node.y + nodeRadius(node) + 15"
                text-anchor="middle"
                class="select-none fill-zinc-500 font-normal"
                :opacity="labelOpacity(node) * nodeVisualOpacity(node)"
                :style="{ fontSize: `${labelSize(node)}px` }"
              >
                {{ node.name.length > 14 ? `${node.name.slice(0, 14)}…` : node.name }}
              </text>
            </g>
          </g>
        </svg>
      </div>

      <!-- 底部统计 -->
      <div class="graph-meta-bar">
        <span>{{ layoutEntityCount }} 实体</span>
        <span class="graph-meta-divider" />
        <span>{{ graph.edge_count }} 关系</span>
        <span v-if="matchedEdgeCount !== graph.edge_count" class="graph-meta-muted">
          已绘制 {{ matchedEdgeCount }}
        </span>
        <span v-if="hiddenEntityCount > 0" class="graph-meta-muted">
          <button type="button" class="graph-meta-link" @click="toggleShowAllEntities">
            {{ showAllEntities ? "仅看关联" : `+${hiddenEntityCount} 隐藏` }}
          </button>
        </span>
        <span class="graph-meta-status">
          {{ selectedId ? "节点聚焦" : focusId ? "链路预览" : "" }}
        </span>
      </div>

      <!-- 聚类 / 社区标签栏 -->
      <div class="graph-community-bar">
        <span class="graph-community-bar-label">
          {{ graph.communities.length ? "社区聚类" : "实体聚类" }}
        </span>
        <div class="graph-community-bar-track">
          <template v-if="graph.communities.length">
            <button
              type="button"
              class="graph-community-tag"
              :class="{ 'graph-community-tag--active': !activeCommunityId }"
              @click="activeCommunityId = null"
            >
              全部
            </button>
            <button
              v-for="community in graph.communities"
              :key="community.community_id"
              type="button"
              class="graph-community-tag"
              :class="{ 'graph-community-tag--active': activeCommunityId === community.community_id }"
              @click="toggleCommunity(community.community_id)"
            >
              {{ community.community_id }}
              <span class="graph-community-tag-count">{{ community.entity_names.length }}</span>
            </button>
          </template>
          <template v-else>
            <button
              v-for="(style, type) in ENTITY_STYLES"
              :key="type"
              type="button"
              class="graph-community-tag"
              :class="{ 'graph-community-tag--active': typeFilter[type] }"
              @click="typeFilter[type] = !typeFilter[type]"
            >
              <span
                class="graph-community-tag-dot"
                :style="{ background: style.color }"
              />
              {{ style.label }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
