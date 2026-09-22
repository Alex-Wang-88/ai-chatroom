import { describe, expect, it } from 'vitest'
import { standardAgentName, standardModelName } from './modelNames'

describe('standard model names', () => {
  it('maps internal handles to user-facing names', () => {
    expect(standardModelName('deepseekv4lash')).toBe('DeepSeek V4 Flash')
    expect(standardModelName('qwen36flash')).toBe('Qwen 3.6 Flash')
    expect(standardModelName('glm5.3flash')).toBe('GPT-5 nano')
  })

  it('prefers the canonical handle over a legacy display label', () => {
    expect(standardAgentName('qwen36flash', '千问3.6flash')).toBe('Qwen 3.6 Flash')
  })
})
