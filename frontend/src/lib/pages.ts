export function parsePageNumbers(value: string): number[] {
  const pages = new Set<number>()
  for (const token of value.split(/[，,\s]+/).filter(Boolean)) {
    const [startText, endText] = token.split(/[-–—]/)
    const start = Number(startText)
    const end = Number(endText ?? startText)
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end - start > 200) continue
    for (let page = start; page <= end; page += 1) pages.add(page)
  }
  return [...pages].sort((a, b) => a - b)
}
