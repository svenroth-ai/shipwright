export interface ApiResponse<T> {
  data: T;
}

export interface ApiError {
  error: string;
  detail?: string;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  total: number;
  offset: number;
  limit: number;
}
