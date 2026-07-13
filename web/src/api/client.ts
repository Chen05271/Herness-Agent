import { getApiBase, getApiKey } from "@/lib/apiConfig";
import type {
  PublicConfigResponse,
  RagGraphResponse,
  RagIngestRequest,
  RagIngestResponse,
  RagSearchRequest,
  RagSearchResponse,
  SessionUsageResponse,
  TaskCancelResponse,
  TaskCreateRequest,
  TaskMessagesResponse,
  TaskStatusResponse,
  TaskSubmitResponse,
  UserUsageResponse,
} from "@/types/herness";

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const apiKey = getApiKey();
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
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

function apiUrl(path: string): string {
  const base = getApiBase().replace(/\/$/, "");
  return `${base}${path}`;
}

export const hernessApi = {
  async submitTask(body: TaskCreateRequest): Promise<TaskSubmitResponse> {
    const res = await fetch(apiUrl("/v1/tasks"), {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async getTask(taskId: string): Promise<TaskStatusResponse> {
    const res = await fetch(apiUrl(`/v1/tasks/${taskId}`), {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async getTaskMessages(taskId: string): Promise<TaskMessagesResponse> {
    const res = await fetch(apiUrl(`/v1/tasks/${taskId}/messages`), {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async cancelTask(taskId: string): Promise<TaskCancelResponse> {
    const res = await fetch(apiUrl(`/v1/tasks/${taskId}`), {
      method: "DELETE",
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async getSessionUsage(
    sessionId: string,
    userId: string,
  ): Promise<SessionUsageResponse> {
    const params = new URLSearchParams({ user_id: userId });
    const res = await fetch(
      apiUrl(`/v1/sessions/${encodeURIComponent(sessionId)}/usage?${params}`),
      { headers: authHeaders() },
    );
    return handleResponse(res);
  },

  async getUserUsage(userId: string): Promise<UserUsageResponse> {
    const res = await fetch(apiUrl(`/v1/users/${encodeURIComponent(userId)}/usage`), {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },

  async getPublicConfig(): Promise<PublicConfigResponse> {
    const res = await fetch(apiUrl("/v1/config/public"), { headers: authHeaders() });
    return handleResponse(res);
  },

  async healthCheck(): Promise<{ status: string }> {
    const res = await fetch(apiUrl("/health"), { headers: authHeaders() });
    return handleResponse(res);
  },

  async ragIngest(body: RagIngestRequest): Promise<RagIngestResponse> {
    const res = await fetch(apiUrl("/v1/rag/ingest"), {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async ragSearch(body: RagSearchRequest): Promise<RagSearchResponse> {
    const res = await fetch(apiUrl("/v1/rag/search"), {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    return handleResponse(res);
  },

  async ragGraph(collectionId: string): Promise<RagGraphResponse> {
    const params = new URLSearchParams({ collection_id: collectionId });
    const res = await fetch(apiUrl(`/v1/rag/graph?${params}`), {
      headers: authHeaders(),
    });
    return handleResponse(res);
  },
};
