import { useEffect, useRef } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import type { FieldError } from '../../types/api'

type Props = { open: boolean; title: string; message: string; errors?: FieldError[]; traceId?: string; onClose: () => void }

export function ErrorModal({ open, title, message, errors = [], traceId, onClose }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (!open) return
    previousFocus.current = document.activeElement as HTMLElement
    document.body.style.overflow = 'hidden'
    dialogRef.current?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>('button, [href], input, [tabindex]:not([tabindex="-1"])')
        if (!focusable.length) return
        const first = focusable[0]; const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.body.style.overflow = ''; document.removeEventListener('keydown', keydown); previousFocus.current?.focus() }
  }, [open, onClose])
  if (!open) return null
  return <div className="modalOverlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1} ref={dialogRef}>
      <button className="iconButton modalClose" onClick={onClose} aria-label="Закрыть"><X size={19} /></button>
      <div className="modalIcon"><AlertTriangle size={22} /></div>
      <h2 id="modal-title">{title}</h2>
      <p>{message}</p>
      {errors.length > 0 && <ul>{errors.map((error) => <li key={`${error.field}-${error.message}`}><strong>{error.field}</strong>: {error.message}</li>)}</ul>}
      {traceId && <div className="trace"><span>Trace ID</span><code>{traceId}</code><small>Сообщите его поддержке</small></div>}
      <button className="primaryButton modalAction" onClick={onClose}>Понятно</button>
    </div>
  </div>
}
