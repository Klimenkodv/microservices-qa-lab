import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { ProfileEditor } from './ProfileEditor'
import { authApi } from '../../api/authApi'
import { ApiError } from '../../types/api'

vi.mock('../../api/authApi', () => ({ authApi: { getProfile: vi.fn(), updateProfile: vi.fn() } }))
const profile = { user_id: 'u', first_name: 'Vadim', last_name: '', birth_date: '', city: '', country: '', description: '', created_at: '', updated_at: '' }
beforeEach(() => vi.resetAllMocks())

test('loads and saves editable profile', async () => {
  vi.mocked(authApi.getProfile).mockResolvedValue(profile)
  vi.mocked(authApi.updateProfile).mockResolvedValue({ ...profile, city: 'Moscow' })
  render(<ProfileEditor token="token" />)
  await screen.findByDisplayValue('Vadim')
  fireEvent.change(screen.getByLabelText('Город'), { target: { value: 'Moscow' } })
  fireEvent.change(screen.getByLabelText('Дата рождения'), { target: { value: '1990-05-21' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
  await screen.findByText('Изменения сохранены')
  expect(authApi.updateProfile).toHaveBeenCalledWith('token', expect.objectContaining({ city: 'Moscow', birth_date: '1990-05-21' }))
})

test('shows pending creation and permits manual refresh', async () => {
  vi.mocked(authApi.getProfile).mockRejectedValueOnce(new ApiError(404, 'PROFILE_NOT_READY', 'pending')).mockResolvedValue(profile)
  render(<ProfileEditor token="token" />)
  await screen.findByText(/Профиль ещё создаётся/)
  fireEvent.click(screen.getByRole('button', { name: 'Обновить профиль' }))
  await screen.findByDisplayValue('Vadim')
})

test('unavailable profile does not remove the session', async () => {
  vi.mocked(authApi.getProfile).mockRejectedValue(new ApiError(503, 'PROFILE_UNAVAILABLE', 'offline'))
  render(<ProfileEditor token="token" />)
  await screen.findByRole('alert')
  expect(screen.getByRole('alert')).toHaveTextContent('Сервис профиля недоступен')
})

test('save failure retains the draft', async () => {
  vi.mocked(authApi.getProfile).mockResolvedValue(profile)
  vi.mocked(authApi.updateProfile).mockRejectedValue(new ApiError(400, 'INVALID_PROFILE', 'Invalid birth date'))
  render(<ProfileEditor token="token" />)
  await screen.findByDisplayValue('Vadim')
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Invalid birth date'))
  expect(screen.getByLabelText('Имя')).toHaveValue('Vadim')
})
