import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { z } from 'zod'

const schema = z.object({
  email: z.string().trim().min(1, 'Укажите email').email('Введите корректный email').max(254, 'Не более 254 символов'),
  password: z.string().min(8, 'Минимум 8 символов').max(72, 'Не более 72 символов').regex(/[A-Za-zА-Яа-я]/, 'Добавьте хотя бы одну букву').regex(/\d/, 'Добавьте хотя бы одну цифру'),
})
export type RegistrationValues = z.infer<typeof schema>
type Props = { onSubmit: (values: RegistrationValues) => Promise<void>; serverErrors?: Record<string, string> }

export function RegistrationForm({ onSubmit, serverErrors = {} }: Props) {
  const [showPassword, setShowPassword] = useState(false)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegistrationValues>({ resolver: zodResolver(schema), mode: 'onTouched' })
  return <form onSubmit={handleSubmit(onSubmit)} noValidate>
    <div className="field">
      <label htmlFor="email">Email</label>
      <input id="email" type="email" autoComplete="email" placeholder="student@example.com" aria-invalid={Boolean(errors.email || serverErrors.email)} {...register('email')} />
      <p className="fieldError" aria-live="polite">{errors.email?.message ?? serverErrors.email ?? ''}</p>
    </div>
    <div className="field">
      <label htmlFor="password">Пароль</label>
      <div className="passwordInput">
        <input id="password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder="8–72 символа" aria-invalid={Boolean(errors.password || serverErrors.password)} {...register('password')} />
        <button type="button" className="iconButton" aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'} onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={19} /> : <Eye size={19} />}</button>
      </div>
      <p className="fieldHint">Минимум одна буква и одна цифра</p>
      <p className="fieldError" aria-live="polite">{errors.password?.message ?? serverErrors.password ?? ''}</p>
    </div>
    <button className="primaryButton submitButton" type="submit" disabled={isSubmitting}>{isSubmitting ? <><LoaderCircle className="spinner" size={18} /> Создаём аккаунт…</> : 'Создать аккаунт'}</button>
  </form>
}
