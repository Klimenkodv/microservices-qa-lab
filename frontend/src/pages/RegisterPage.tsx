import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, Database, Mail, Radio } from 'lucide-react'
import { ErrorModal } from '../components/ErrorModal/ErrorModal'
import { RegistrationForm, type RegistrationValues } from '../components/RegistrationForm/RegistrationForm'
import { useAuth } from '../hooks/useAuth'
import { ApiError, type FieldError } from '../types/api'

type ModalState = { title: string; message: string; errors?: FieldError[]; traceId?: string } | null

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [modal, setModal] = useState<ModalState>(null)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const closeModal = useCallback(() => setModal(null), [])
  async function submit(values: RegistrationValues) {
    setServerErrors({})
    try {
      await register(values.email, values.password)
      navigate('/profile', { replace: true })
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError(null, 'UNKNOWN', 'Не удалось выполнить запрос')
      if (apiError.status === 400) {
        setServerErrors(Object.fromEntries(apiError.fieldErrors.map((item) => [item.field, item.message])))
        setModal({ title: 'Проверьте данные', message: 'Исправьте отмеченные поля и отправьте форму снова.', errors: apiError.fieldErrors })
      } else if (apiError.status === 409) {
        setServerErrors({ email: 'Этот email уже зарегистрирован' })
        setModal({ title: 'Аккаунт уже существует', message: `Для ${values.email} уже создан аккаунт. Укажите другой email.`, traceId: apiError.traceId })
      } else {
        setModal({ title: 'Сервис временно недоступен', message: 'Регистрацию не удалось завершить. Попробуйте ещё раз через несколько минут.', traceId: apiError.traceId })
      }
    }
  }
  return <main className="authLayout">
    <section className="labPanel" aria-label="Схема учебного стенда">
      <div className="brand"><span className="brandMark"><Activity size={22} /></span><span>QA Flow Lab</span></div>
      <div className="labCopy"><p className="eyebrow">Микросервисы в действии</p><h1>Одна регистрация.<br />Вся цепочка событий.</h1><p>Создайте учебный аккаунт и проследите, как данные проходят через API, Kafka и независимые сервисы.</p></div>
      <div className="flow" aria-hidden="true">
        <div className="flowItem active"><Activity size={18} /><span>Auth API</span></div><span className="flowLine" />
        <div className="flowItem"><Radio size={18} /><span>Kafka</span></div><span className="flowLine" />
        <div className="flowBranches"><div className="flowItem"><Mail size={18} /><span>Email</span></div><div className="flowItem"><Database size={18} /><span>Stats</span></div></div>
      </div>
      <p className="labFoot">Локальный учебный стенд · реальные письма не отправляются</p>
    </section>
    <section className="formPanel">
      <div className="formShell"><p className="step">Шаг 1 из 1</p><h2>Создание аккаунта</h2><p className="lead">Используйте тестовые данные. После регистрации откроется профиль пользователя.</p><RegistrationForm onSubmit={submit} serverErrors={serverErrors} /><p className="privacy">Данные хранятся только в локальном учебном окружении.</p></div>
    </section>
    <ErrorModal open={Boolean(modal)} title={modal?.title ?? ''} message={modal?.message ?? ''} errors={modal?.errors} traceId={modal?.traceId} onClose={closeModal} />
  </main>
}
