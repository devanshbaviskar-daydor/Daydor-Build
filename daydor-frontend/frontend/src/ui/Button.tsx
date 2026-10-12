import { forwardRef, type ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'quiet'
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: Variant; busy?: boolean }

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = 'secondary', busy, disabled, className = '', children, type = 'button', ...rest }, ref) {
  const v = variant === 'secondary' ? '' : `btn-${variant}`
  return (
    <button ref={ref} type={type} className={`btn ${v} ${className}`.trim()} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy ? 'Working…' : children}
    </button>
  )
})
