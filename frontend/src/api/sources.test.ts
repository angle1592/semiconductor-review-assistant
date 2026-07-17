import { afterEach, expect, it, vi } from 'vitest'

import { sourcesApi } from './sources'


afterEach(() => vi.unstubAllGlobals())

it('loads every source block page instead of stopping at the first 100', async () => {
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const count = offset === 0 ? 100 : 50
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: Array.from({ length: count }, (_, index) => ({
          id: `block-${offset + index}`,
          ordinal: offset + index,
          locator: `slide:${offset + index + 1}`,
          kind: 'paragraph',
          text: `内容 ${offset + index + 1}`,
          page_number: offset + index + 1,
          heading_path: [],
          preview_path: null,
        })),
        total: 150,
        offset,
        limit: 100,
      }),
    }
  })
  vi.stubGlobal('fetch', fetchMock)

  const result = await sourcesApi.blocks(1)

  expect(result.items).toHaveLength(150)
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(String(fetchMock.mock.calls[0][0])).toContain('limit=100')
  expect(String(fetchMock.mock.calls[1][0])).toContain('offset=100')
})
