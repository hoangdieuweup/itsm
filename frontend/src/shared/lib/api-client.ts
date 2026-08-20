/**
 * Thin fetch wrapper that unwraps the backend's `{ success, data, error }` envelope
 * exactly once, so fetchers downstream (in modules/entities) work with the plain
 * payload and never need to know the envelope exists.
 *
 * See .claude/skills/nextjs-modular-architecture/references/data-layer.md.
 */
export interface ApiErrorPayload {
  code: string;
  message: string;
  context?: Record<string, unknown>;
}

export class ApiRequestError extends Error {
  code: string;
  context?: Record<string, unknown>;

  constructor(code: string, message: string, context?: Record<string, unknown>) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.context = context;
  }
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorPayload | null;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    credentials: "include",
    ...init,
  });

  const body = (await res.json()) as ApiEnvelope<T>;

  if (!body.success || body.error) {
    const error = body.error ?? { code: "unknown_error", message: res.statusText };
    throw new ApiRequestError(error.code, error.message, error.context);
  }

  return body.data as T;
}
