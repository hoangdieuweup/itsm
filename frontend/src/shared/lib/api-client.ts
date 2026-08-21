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

interface PendingRequest {
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
}

let isRefreshing = false;
let pendingQueue: PendingRequest[] = [];

function flushPendingQueue(error: Error | null): void {
  pendingQueue.forEach((item) => {
    if (error) {
      item.reject(error);
    } else {
      item.resolve();
    }
  });
  pendingQueue = [];
}

function isAuthBypassUrl(url?: string): boolean {
  if (!url) return false;
  return (
    url.includes("/auth/refresh") ||
    url.includes("/auth/oauth") ||
    url.includes("/auth/logout")
  );
}

function shouldAttemptTokenRefresh(
  error: AxiosError<ApiEnvelope<unknown>>,
  config?: AxiosRequestConfig & { _retry?: boolean },
): boolean {
  if (typeof window === "undefined" || !config || config._retry) {
    return false;
  }
  if (isAuthBypassUrl(config.url)) {
    return false;
  }
  const is401 = error.response?.status === 401;
  const isAuthCode = error.response?.data?.error?.code === "auth_not_authenticated";
  return is401 || isAuthCode;
}

async function handleSilentRefresh(
  originalConfig: AxiosRequestConfig & { _retry?: boolean },
): Promise<unknown> {
  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      pendingQueue.push({ resolve, reject });
    }).then(() => apiClient.request(originalConfig));
  }

  originalConfig._retry = true;
  isRefreshing = true;

  try {
    await apiClient.post(API_CONFIG.ENDPOINTS.AUTH.REFRESH);
    flushPendingQueue(null);
    return await apiClient.request(originalConfig);
  } catch (refreshErr) {
    const err =
      refreshErr instanceof Error ? refreshErr : new Error("Token refresh failed");
    flushPendingQueue(err);
    throw refreshErr;
  } finally {
    isRefreshing = false;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiEnvelope<unknown>>) => {
    const originalConfig = error.config as
      | (AxiosRequestConfig & { _retry?: boolean })
      | undefined;

    if (originalConfig && shouldAttemptTokenRefresh(error, originalConfig)) {
      try {
        return await handleSilentRefresh(originalConfig);
      } catch (refreshError) {
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);

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
