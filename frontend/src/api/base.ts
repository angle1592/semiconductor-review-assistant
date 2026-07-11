export function resolveApiBaseUrl(
  configured: string | undefined,
  development: boolean,
  origin: string,
): string {
  const selected = configured || (development ? 'http://127.0.0.1:8000' : origin)
  return selected.replace(/\/$/, '')
}
