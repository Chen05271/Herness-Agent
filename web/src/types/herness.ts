export type TaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "timeout"
  | "aborted"
  | "cancelled";

export type AgentRole = "supervisor" | "worker" | "critic" | "orchestrator";

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  requests?: number;
  tool_calls?: number;
}

export type Persona = "consumer" | "merchant";

export interface TaskMessage {
  id: string;
  role: AgentRole;
  round_index: number;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TaskCreateRequest {
  user_id: string;
  session_id: string;
  input: string;
  metadata?: {
    persona?: Persona;
    allowed_tools?: string[];
  };
  task_id?: string | null;
}

export interface TaskSubmitResponse {
  task_id: string;
  status: TaskStatus;
  created_at: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: TaskStatus;
  answer: string;
  error: string;
  rounds_used: number;
  usage: TokenUsage;
  created_at: string;
  updated_at: string;
}

export interface TaskMessagesResponse {
  task_id: string;
  messages: TaskMessage[];
}

export interface SessionUsageResponse {
  user_id: string;
  session_id: string;
  usage: TokenUsage;
}

export interface UserUsageResponse {
  user_id: string;
  usage: TokenUsage;
}

export interface PublicConfigFeatures {
  rag_enabled: boolean;
  dreaming_enabled: boolean;
  hereness_enabled: boolean;
  agri_commerce_enabled: boolean;
}

export interface PublicConfigLimits {
  token_budget_per_user: number;
  token_budget_per_session: number;
}

export interface PublicConfigResponse {
  llm_model: string;
  api_version: string;
  features: PublicConfigFeatures;
  limits: PublicConfigLimits;
}

export interface TaskCancelResponse {
  task_id: string;
  status: TaskStatus;
}

export interface TaskFinishedEvent {
  event: "task_finished";
  task_id: string;
  status: TaskStatus;
  usage?: TokenUsage;
}

export type StreamEvent = TaskMessage | TaskFinishedEvent;

export function isTaskFinishedEvent(
  event: StreamEvent,
): event is TaskFinishedEvent {
  return "event" in event && event.event === "task_finished";
}

export interface ChatSession {
  id: string;
  persona: Persona;
  userId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  taskId?: string;
  status?: TaskStatus;
  progressText?: string;
  error?: string;
  trace?: TaskMessage[];
  usage?: TokenUsage;
  createdAt: string;
}

export interface PersonaContext {
  persona: Persona;
  userId: string;
}

export interface RagIngestRequest {
  collection_id: string;
  collection_name?: string;
  text: string;
  source?: string;
  persona?: Persona | null;
  build_communities?: boolean;
}

export interface RagIngestResponse {
  chunk_ids: number[];
  collection_id: string;
  communities_built: number;
}

export interface RagSearchRequest {
  query: string;
  collection_id: string;
}

export interface RagHit {
  chunk_id: number;
  content: string;
  score: number;
  source: string;
  retrieval_channel: string;
}

export interface RagSearchResponse {
  query: string;
  collection_id: string;
  hits: RagHit[];
  coarse_count: number;
  fine_count: number;
}

export interface RagGraphEntity {
  name: string;
  entity_type: string;
  chunk_ids: number[];
}

export interface RagGraphEdge {
  source: string;
  target: string;
  relation: string;
  chunk_id: number | null;
}

export interface RagGraphCommunity {
  community_id: string;
  summary: string;
  entity_names: string[];
}

export interface RagGraphResponse {
  collection_id: string;
  entities: RagGraphEntity[];
  edges: RagGraphEdge[];
  communities: RagGraphCommunity[];
  entity_count: number;
  edge_count: number;
  community_count: number;
}
