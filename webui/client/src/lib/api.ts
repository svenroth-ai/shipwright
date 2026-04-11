import type { ApiResponse, ApiError as ApiErrorType } from '../types';

export const API_BASE = '/api';

export class ApiError extends Error {
  error: string;
  detail?: string;
  status: number;

  constructor(status: number, body: ApiErrorType) {
    super(body.error);
    this.name = 'ApiError';
    this.error = body.error;
    this.detail = body.detail;
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);

  if (!response.ok) {
    let body: ApiErrorType;
    try {
      body = await response.json();
    } catch {
      body = { error: response.statusText };
    }
    throw new ApiError(response.status, body);
  }

  const json: ApiResponse<T> = await response.json();
  return json.data;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
