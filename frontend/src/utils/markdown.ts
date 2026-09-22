// CommonMark treats CJK quote characters as punctuation delimiters.  A
// frequent model output such as **“重点”** can therefore remain literal even
// though the author clearly intended emphasis.  Move the quote marks outside
// the emphasis span before parsing; the rendered text is unchanged.
const CJK_QUOTED_EMPHASIS = /\*\*([“‘「『（《【〔〈])([^*\n]+?)([”’」』）》】〕〉])\*\*/gu

export function prepareMarkdown(content: string): string {
  return content.replace(CJK_QUOTED_EMPHASIS, '$1**$2**$3')
}
