import { describe, expect, it } from 'vitest'

import { parsePageNumbers } from './pages'

describe('parsePageNumbers', () => {
  it('normalizes ranges, Chinese commas, duplicates, and invalid input', () => {
    expect(parsePageNumbers('3-5，5, 8, bad')).toEqual([3, 4, 5, 8])
  })
})
