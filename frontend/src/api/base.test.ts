import { describe, expect, it } from 'vitest'

import { resolveApiBaseUrl } from './base'

describe('resolveApiBaseUrl', () => {
  it('uses the serving origin in production and the backend port in development', () => {
    expect(resolveApiBaseUrl(undefined, false, 'http://127.0.0.1:8765')).toBe('http://127.0.0.1:8765')
    expect(resolveApiBaseUrl(undefined, true, 'http://127.0.0.1:5173')).toBe('http://127.0.0.1:8000')
    expect(resolveApiBaseUrl('https://models.local/', false, 'http://localhost')).toBe('https://models.local')
  })
})
