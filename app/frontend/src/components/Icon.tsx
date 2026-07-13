interface Props {
  name: string
  className?: string
  /** Visual pixel size; maps to font-size + optical-size axis. */
  size?: number
  filled?: boolean
}

/** Material Symbols (Outlined) glyph. */
export function Icon({ name, className = '', size = 24, filled = false }: Props) {
  return (
    <span
      className={`material-symbols-outlined select-none ${className}`}
      style={{
        fontSize: size,
        fontVariationSettings: `'FILL' ${filled ? 1 : 0}, 'wght' 400, 'GRAD' 0, 'opsz' ${size}`,
      }}
      aria-hidden="true"
    >
      {name}
    </span>
  )
}
