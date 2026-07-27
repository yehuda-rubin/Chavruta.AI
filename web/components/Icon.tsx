// Material Symbols icon (self-hosted font — see globals.css / fonts.local.css).
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  return <span className={`material-symbols-outlined ${className}`}>{name}</span>;
}
