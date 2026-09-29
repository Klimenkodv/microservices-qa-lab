import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, CalendarDays, Check, Copy, LogOut, Mail, UserRound } from 'lucide-react'
import { ErrorModal } from '../components/ErrorModal/ErrorModal'
import { useAuth } from '../hooks/useAuth'
import { ApiError } from '../types/api'

export function ProfilePage() {
  const auth = useAuth(); const navigate = useNavigate()
  const [loading, setLoading] = useState(!auth.user)
  const [sessionEnded, setSessionEnded] = useState(false)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (auth.user) return
    auth.loadProfile().catch((error) => {
      auth.logout()
      if (error instanceof ApiError && error.status === 401) setSessionEnded(true)
      else navigate('/register', { replace: true })
    }).finally(() => setLoading(false))
  }, [])
  const closeSessionModal = useCallback(() => { setSessionEnded(false); navigate('/register', { replace: true }) }, [navigate])
  if (loading) return <main className="loadingScreen"><Activity className="spinner" size={30} /><p>Загружаем профиль…</p></main>
  if (!auth.user) return <ErrorModal open={sessionEnded} title="Сессия завершена" message="Войдите снова, чтобы продолжить работу." onClose={closeSessionModal} />
  const createdAt = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(auth.user.created_at))
  async function copyId() { await navigator.clipboard.writeText(auth.user!.user_id); setCopied(true); window.setTimeout(() => setCopied(false), 1500) }
  return <main className="profileLayout">
    <header className="profileHeader"><div className="brand dark"><span className="brandMark"><Activity size={22} /></span><span>QA Flow Lab</span></div><button className="secondaryButton" onClick={() => { auth.logout(); navigate('/register', { replace: true }) }}><LogOut size={17} /> Выйти</button></header>
    <section className="profileContent"><div className="successBadge"><Check size={18} /> Регистрация завершена</div><h1>Личный кабинет</h1><p className="lead">Профиль получен из auth-service по сохранённому access token.</p>
      <div className="profileCard"><div className="avatar"><UserRound size={30} /></div><div className="profileIdentity"><span>Пользователь</span><strong>{auth.user.email}</strong></div><dl>
        <div><dt><Mail size={16} /> Email</dt><dd>{auth.user.email}</dd></div>
        <div><dt><CalendarDays size={16} /> Создан</dt><dd>{createdAt}</dd></div>
        <div><dt><UserRound size={16} /> User ID</dt><dd><code>{auth.user.user_id}</code><button className="iconButton" onClick={copyId} aria-label="Скопировать User ID">{copied ? <Check size={17} /> : <Copy size={17} />}</button></dd></div>
      </dl></div>
      <div className="nextSteps"><h2>Что произошло дальше</h2><div className="statusGrid"><div><span className="statusDot" /><strong>Событие опубликовано</strong><small>user.registered.v1</small></div><div><span className="statusDot waiting" /><strong>Обработка асинхронна</strong><small>Проверьте Kafka UI и Mailpit</small></div></div></div>
    </section>
  </main>
}
