export type User = { user_id: string; email: string; created_at: string }
export type RegisterResponse = User & { access_token: string; token_type: 'bearer' }
export type PersonalProfile = {
  user_id: string; first_name: string; last_name: string; birth_date: string
  city: string; country: string; description: string; created_at: string; updated_at: string
}
export type ProfileChanges = Pick<PersonalProfile, 'first_name' | 'last_name' | 'birth_date' | 'city' | 'country' | 'description'>
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
