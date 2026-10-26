import { API_BASE_URL } from '@/lib/constants';
import { createClient } from '@/lib/supabase/client';
import { resolveOrgId } from '@/components/providers/OrgContext';

export class ApiError extends Error {
  public status: number;
  public data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export interface RequestConfig extends Omit<RequestInit, 'body'> {
  body?: any;
  orgId?: string | null;
  params?: Record<string, string | number | boolean | undefined | null>;
}

let cachedToken: string | null = null;
let tokenExpiresAt = 0;
let authListenerInitialized = false;

async function getAuthToken(): Promise<string | null> {
  if (typeof window === 'undefined') {
    return null;
  }
  const now = Date.now();
  if (cachedToken && tokenExpiresAt > now + 60000) {
    return cachedToken;
  }
  try {
    const supabase = createClient();
    if (!authListenerInitialized) {
      authListenerInitialized = true;
      supabase.auth.onAuthStateChange((_, session) => {
        cachedToken = session?.access_token || null;
        tokenExpiresAt = session?.expires_at ? session.expires_at * 1000 : 0;
      });
    }
    const { data } = await supabase.auth.getSession();
    cachedToken = data.session?.access_token || null;
    tokenExpiresAt = data.session?.expires_at ? data.session.expires_at * 1000 : 0;
    return cachedToken;
  } catch {
    return null;
  }
}

function buildUrl(endpoint: string, params?: RequestConfig['params']): string {
  const base = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
  if (!params) {
    return base;
  }

  const url = new URL(base);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.append(key, String(value));
    }
  });
  return url.toString();
}

async function request<T>(endpoint: string, config: RequestConfig = {}): Promise<T> {
  const { body, headers = {}, orgId, params, signal, ...customConfig } = config;
  const token = await getAuthToken();
  const effectiveOrgId = orgId || (typeof window !== 'undefined' ? resolveOrgId() : null);

  const isJsonBody = body !== undefined && !(body instanceof FormData) && !(body instanceof Blob);

  const requestHeaders: Record<string, string> = {
    ...(headers as Record<string, string>),
  };

  if (isJsonBody) {
    requestHeaders['Content-Type'] = 'application/json';
  }

  if (token) {
    requestHeaders['Authorization'] = `Bearer ${token}`;
  }

  if (effectiveOrgId) {
    requestHeaders['X-Org-Id'] = effectiveOrgId;
  }

  const finalUrl = buildUrl(endpoint, params);

  const response = await fetch(finalUrl, {
    ...customConfig,
    signal,
    headers: requestHeaders,
    body: isJsonBody ? JSON.stringify(body) : body,
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    let errorPayload: any = null;
    try {
      errorPayload = await response.json();
      if (errorPayload?.detail) {
        errorDetail = typeof errorPayload.detail === 'string' 
          ? errorPayload.detail 
          : JSON.stringify(errorPayload.detail);
      } else if (errorPayload?.message) {
        errorDetail = errorPayload.message;
      }
    } catch {
      try {
        errorDetail = await response.text();
      } catch {}
    }
    throw new ApiError(response.status, errorDetail || `Request failed with status ${response.status}`, errorPayload);
  }

  if (response.status === 204) {
    return null as T;
  }

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }

  return response.text() as unknown as T;
}

export const httpClient = {
  get: <T>(endpoint: string, config?: RequestConfig) =>
    request<T>(endpoint, { ...config, method: 'GET' }),

  post: <T>(endpoint: string, body?: any, config?: RequestConfig) =>
    request<T>(endpoint, { ...config, method: 'POST', body }),

  patch: <T>(endpoint: string, body?: any, config?: RequestConfig) =>
    request<T>(endpoint, { ...config, method: 'PATCH', body }),

  put: <T>(endpoint: string, body?: any, config?: RequestConfig) =>
    request<T>(endpoint, { ...config, method: 'PUT', body }),

  delete: <T>(endpoint: string, config?: RequestConfig) =>
    request<T>(endpoint, { ...config, method: 'DELETE' }),
};
