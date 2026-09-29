import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RegistrationForm } from './RegistrationForm'

describe('RegistrationForm', () => {
  it('shows required validation errors', async () => {
    render(<RegistrationForm onSubmit={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Создать аккаунт' }))
    expect(await screen.findByText('Укажите email')).toBeInTheDocument()
    expect(screen.getByText('Минимум 8 символов')).toBeInTheDocument()
  })

  it('rejects a password without a digit', async () => {
    render(<RegistrationForm onSubmit={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Email'), 'student@example.com')
    await userEvent.type(screen.getByLabelText('Пароль'), 'PasswordOnly')
    await userEvent.click(screen.getByRole('button', { name: 'Создать аккаунт' }))
    expect(await screen.findByText('Добавьте хотя бы одну цифру')).toBeInTheDocument()
  })

  it('submits valid values once', async () => {
    const submit = vi.fn().mockResolvedValue(undefined)
    render(<RegistrationForm onSubmit={submit} />)
    await userEvent.type(screen.getByLabelText('Email'), 'student@example.com')
    await userEvent.type(screen.getByLabelText('Пароль'), 'Password123')
    await userEvent.click(screen.getByRole('button', { name: 'Создать аккаунт' }))
    expect(submit).toHaveBeenCalledWith({ email: 'student@example.com', password: 'Password123' }, expect.anything())
  })

  it('renders server field errors', () => {
    render(<RegistrationForm onSubmit={vi.fn()} serverErrors={{ email: 'Этот email уже зарегистрирован' }} />)
    expect(screen.getByText('Этот email уже зарегистрирован')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
  })
})
