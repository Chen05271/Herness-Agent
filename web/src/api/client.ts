import type {
  RagGraphResponse,
  RagIngestRequest,
  RagIngestResponse,
  RagSearchRequest,
  RagSearchResponse,
  TaskCancelResponse,
  TaskCreateRequest,
  TaskMessagesResponse,
  TaskStatusResponse,
  TaskSubmitResponse,
} from "@/types/herness";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (API_KEY) {
    headers.Authorization = `Bearer ${API_KEY}`;
  }
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const hernessApi = {
  async submitTask(body: TaskCreateRequest): Promise<TaskSubmitResponse> {
    const res = await fetch(`${API_BASE}/v1/tasks`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async getTask(taskId: string): Promise<TaskStatusResponse> {
    const res = await fetch(`${API_BASE}/v1/tasks/${taskId}`, {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async getTaskMessages(taskId: string): Promise<TaskMessagesResponse> {
    const res = await fetch(`${API_BASE}/v1/tasks/${taskId}/messages`, {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async cancelTask(taskId: string): Promise<TaskCancelResponse> {
    const res = await fetch(`${API_BASE}/v1/tasks/${taskId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async healthCheck(): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE}/health`, { headers: authHeaders() });
    return handleResponse(res);
  },

  async ragIngest(body: RagIngestRequest): Promise<RagIngestResponse> {
    const res = await fetch(`${API_BASE}/v1/rag/ingest`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async ragSearch(body: RagSearchRequest): Promise<RagSearchResponse> {
    const res = await fetch(`${API_BASE}/v1/rag/search`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async ragGraph(collectionId: string): Promise<RagGraphResponse> {
    const params = new URLSearchParams({ collection_id: collectionId });
    const res = await fetch(`${API_BASE}/v1/rag/graph?${params}`, {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },
};
