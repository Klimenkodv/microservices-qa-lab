export type User = { user_id: string; email: string; created_at: string }
export type RegisterResponse = User & { access_token: string; token_type: 'bearer' }
export type FieldError = { field: string; message: string }

export class ApiError extends Error {
  constructor(
    public status: number | null,
    public code: string,
    message: string,
    public fieldErrors: FieldError[] = [],
    public traceId?: string,
  ) { super(message); this.name = 'ApiError' }
}
