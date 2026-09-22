import { describe, expect, it } from 'vitest'
import { prepareMarkdown } from './markdown'

describe('prepareMarkdown', () => {
  it('keeps CJK quote marks while making the intended emphasis parseable', () => {
    expect(prepareMarkdown('**“AI 素养”**')).toBe('“**AI 素养**”')
  })

  it('does not rewrite ordinary emphasis', () => {
    expect(prepareMarkdown('**重点**')).toBe('**重点**')
  })
})
