export function formatDateTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hours = d.getHours()
  const ampm = hours >= 12 ? 'PM' : 'AM'
  const h = String(hours % 12 || 12).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  const sec = String(d.getSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${ampm} ${h}:${min}:${sec}`
}
