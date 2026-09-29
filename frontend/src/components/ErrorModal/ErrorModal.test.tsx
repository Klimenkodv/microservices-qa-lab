import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ErrorModal } from './ErrorModal'

describe('ErrorModal', () => {
  it('shows field errors and trace id', () => {
    render(<ErrorModal open title="Проверьте данные" message="Исправьте поля" errors={[{ field: 'email', message: 'Некорректный email' }]} traceId="trace-123" onClose={vi.fn()} />)
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByText(/Некорректный email/)).toBeInTheDocument()
    expect(screen.getByText('trace-123')).toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const close = vi.fn()
    render(<ErrorModal open title="Ошибка" message="Текст" onClose={close} />)
    await userEvent.keyboard('{Escape}')
    expect(close).toHaveBeenCalledOnce()
  })

  it('does not render while closed', () => {
    render(<ErrorModal open={false} title="Ошибка" message="Текст" onClose={vi.fn()} />)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })
})
