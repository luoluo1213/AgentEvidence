const configuredBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
export const API_BASE_URL = configuredBase.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
    public readonly code = "request_failed",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach the AgentEvidence backend.", null, "network_error");
  }

  const payload = await parseResponseBody(response);
  if (!response.ok) {
    const error = isRecord(payload) && isRecord(payload.error) ? payload.error : null;
    const message = error && typeof error.message === "string"
      ? error.message
      : `Request failed with HTTP ${response.status}.`;
    const code = error && typeof error.code === "string" ? error.code : `http_${response.status}`;
    throw new ApiError(message, response.status, code);
  }
  return payload as T;
}

export async function responseError(response: Response): Promise<ApiError> {
  const payload = await parseResponseBody(response);
  const error = isRecord(payload) && isRecord(payload.error) ? payload.error : null;
  return new ApiError(
    error && typeof error.message === "string" ? error.message : `Request failed with HTTP ${response.status}.`,
    response.status,
    error && typeof error.code === "string" ? error.code : `http_${response.status}`,
  );
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("The backend returned an invalid JSON response.", response.status, "invalid_json");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
