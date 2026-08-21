/**
 * Axios-based API client that unwraps the backend's `{ success, data, error }`
 * envelope exactly once, so fetchers downstream (in modules/entities) work with
 * the plain payload and never need to know the envelope exists.
 *
 * For Server Components (SSR/prefetching), forwards incoming cookies from
 * `next/headers` so authenticated requests succeed on the server.
 *
 * See .claude/skills/nextjs-modular-architecture/references/data-layer.md.
 */
import axios, { type AxiosError, type AxiosRequestConfig } from "axios";
import { API_CONFIG } from "@/shared/constants/api";

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

/**
 * Pre-configured axios instance: JSON content type, cookies included
 * (httpOnly session cookies set by the OAuth callback), base URL from API_CONFIG.
 */
export const apiClient = axios.create({
  baseURL: API_CONFIG.API_V1_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

/**
 * Helper to forward cookies when executing on the server (Server Components / SSR).
 */
async function resolveServerCookieHeader(): Promise<string | null> {
  if (typeof window !== "undefined") {
    return null;
  }
  try {
    const { cookies } = await import("next/headers");
    const cookieStore = await cookies();
    return cookieStore.toString();
  } catch {
    return null;
  }
}

/**
 * Helper to normalize any error into an ApiRequestError (complexity < 5).
 */
function normalizeApiError(error: unknown): ApiRequestError {
  if (error instanceof ApiRequestError) {
    return error;
  }

  if (axios.isAxiosError(error)) {
    const axiosErr = error as AxiosError<ApiEnvelope<unknown>>;
    const serverError = axiosErr.response?.data?.error;

    if (serverError) {
      return new ApiRequestError(
        serverError.code,
        serverError.message,
        serverError.context,
      );
    }

    return new ApiRequestError(
      "network_error",
      axiosErr.message || "Network error",
    );
  }

  const message = error instanceof Error ? error.message : "Unknown error";
  return new ApiRequestError("unknown_error", message);
}

/**
 * Unwraps the backend's ApiResponse envelope. Every fetcher calls this
 * instead of `apiClient` directly, so the envelope is invisible downstream.
 */
export async function apiFetch<T>(
  path: string,
  config?: AxiosRequestConfig,
): Promise<T> {
  try {
    const serverCookies = await resolveServerCookieHeader();
    const headers = {
      ...config?.headers,
      ...(serverCookies ? { Cookie: serverCookies } : {}),
    };

    const res = await apiClient.request<ApiEnvelope<T>>({
      url: path,
      ...config,
      headers,
    });

    const body = res.data;

    if (body.error) {
      throw new ApiRequestError(
        body.error.code,
        body.error.message,
        body.error.context,
      );
    }

    if (!body.success) {
      throw new ApiRequestError("unknown_error", "Request failed");
    }

    return body.data as T;
  } catch (error) {
    throw normalizeApiError(error);
  }
}
