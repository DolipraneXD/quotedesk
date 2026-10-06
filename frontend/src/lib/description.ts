import type { DescriptionLine } from '../api/quotes'

/** One spec per line; a line starting with "!" prints in red on the document. */
export function descriptionToText(lines: DescriptionLine[]): string {
  return lines.map((d) => (d.emphasis ? `!${d.text}` : d.text)).join('\n')
}

export function textToDescription(text: string): DescriptionLine[] {
  return text
    .split('\n')
    .map((line) => line.trimEnd())
    .filter((line) => line.trim() !== '')
    .map((line) =>
      line.startsWith('!')
        ? { text: line.slice(1).trim(), emphasis: true }
        : { text: line, emphasis: false },
    )
}
