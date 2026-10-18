import { useEffect, useState, type FormEvent } from 'react'
import { Check, LoaderCircle, RefreshCw, Save } from 'lucide-react'
import { authApi } from '../../api/authApi'
import { ApiError, type ProfileChanges } from '../../types/api'

const empty: ProfileChanges = { first_name: '', last_name: '', birth_date: '', city: '', country: '', description: '' }
type State = 'loading' | 'pending' | 'ready' | 'error'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Сессия завершена. Войдите снова.'
    if (error.code === 'PROFILE_TIMEOUT') return 'Превышено время ожидания профиля. Попробуйте снова.'
    if (error.code === 'INVALID_PROFILE') return error.message
    if (error.fieldErrors.length) return error.fieldErrors.map(field => `${field.field}: ${field.message}`).join('; ')
  }
  return 'Сервис профиля недоступен. Данные учётной записи сохранены.'
}

export function ProfileEditor({ token }: { token: string }) {
  const [state, setState] = useState<State>('loading')
  const [form, setForm] = useState<ProfileChanges>(empty)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempts = 0
    setState('loading'); setError(''); setSaved(false)
    async function load() {
      try {
        const data = await authApi.getProfile(token)
        if (!active) return
        setForm(Object.fromEntries(Object.keys(empty).map(key => [key, data[key as keyof ProfileChanges]])) as ProfileChanges)
        setState('ready')
      } catch (reason) {
        if (!active) return
        if (reason instanceof ApiError && reason.code === 'PROFILE_NOT_READY') {
          setState('pending')
          if (++attempts < 10) timer = setTimeout(load, 2000)
        } else { setState('error'); setError(errorMessage(reason)) }
      }
    }
    void load()
    return () => { active = false; clearTimeout(timer) }
  }, [token, reload])

  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(''); setSaved(false)
    try { await authApi.updateProfile(token, form); setSaved(true) }
    catch (reason) { setError(errorMessage(reason)) }
    finally { setSaving(false) }
  }

  return <section className="personalProfile" aria-labelledby="personal-profile-title">
    <div className="profileSectionHeader"><h2 id="personal-profile-title">Личные данные</h2>
      <button type="button" className="iconButton" title="Обновить профиль" aria-label="Обновить профиль" disabled={state === 'loading' || saving} onClick={() => setReload(value => value + 1)}><RefreshCw size={18} /></button>
    </div>
    {state === 'loading' && <p role="status"><LoaderCircle className="spinner" size={18} /> Загружаем профиль…</p>}
    {state === 'pending' && <p role="status">Профиль ещё создаётся. Учётная запись уже готова.</p>}
    {state === 'error' && <p role="alert" className="fieldError">{error}</p>}
    {state === 'ready' && <form onSubmit={save}>
      <div className="profileFields">
        {([['first_name', 'Имя'], ['last_name', 'Фамилия'], ['birth_date', 'Дата рождения'], ['city', 'Город'], ['country', 'Страна']] as const).map(([key, label]) => <div className="field" key={key}>
          <label htmlFor={`profile-${key}`}>{label}</label>
          <input id={`profile-${key}`} type={key === 'birth_date' ? 'date' : 'text'} maxLength={key === 'birth_date' ? undefined : 100} value={form[key]} disabled={saving}
            onChange={event => { setForm(value => ({ ...value, [key]: event.target.value })); setSaved(false) }} />
        </div>)}
        <div className="field profileDescription"><label htmlFor="profile-description">О себе</label>
          <textarea id="profile-description" maxLength={2000} rows={4} value={form.description} disabled={saving}
            onChange={event => { setForm(value => ({ ...value, description: event.target.value })); setSaved(false) }} />
        </div>
      </div>
      {error && <p role="alert" className="fieldError">{error}</p>}
      <div className="profileActions"><button className="primaryButton" disabled={saving} type="submit">{saving ? <LoaderCircle className="spinner" size={18} /> : <Save size={18} />} Сохранить</button>
        {saved && <span role="status"><Check size={18} /> Изменения сохранены</span>}
      </div>
    </form>}
  </section>
}
