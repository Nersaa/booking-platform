// The listing's photo, or a drawn placeholder: demo listings are seeded without photos.

type Props = { url: string | null | undefined; propertyType: string; className?: string }

export default function Cover({ url, propertyType, className = '' }: Props) {
  if (url) {
    return <img className={`cover ${className}`} src={url} alt="" loading="lazy" />
  }
  const isHouse = propertyType === 'house' || propertyType === 'cottage'
  return (
    <div className={`cover cover-empty ${className}`} aria-hidden="true">
      <svg viewBox="0 0 64 48" width="64" height="48">
        {isHouse ? (
          <path d="M8 26 32 8l24 18M14 22v20h36V22M27 42V30h10v12" />
        ) : (
          <path d="M16 42V8h32v34M10 42h44M24 16h4M36 16h4M24 24h4M36 24h4M24 32h4M36 32h4" />
        )}
      </svg>
    </div>
  )
}
