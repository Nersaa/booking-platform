export function money(minorUnits: number, currency: string): string {
  return new Intl.NumberFormat('en', {
    style: 'currency',
    currency,
    maximumFractionDigits: minorUnits % 100 === 0 ? 0 : 2,
  }).format(minorUnits / 100)
}

export function shortDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en', { day: 'numeric', month: 'short' })
}

export function time(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}
