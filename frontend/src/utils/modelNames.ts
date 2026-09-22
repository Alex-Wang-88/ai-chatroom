const STANDARD_NAMES: Record<string, string> = {
  deepseekv4lash: 'DeepSeek V4 Flash',
  deepseekv4flash: 'DeepSeek V4 Flash',
  deepseek: 'DeepSeek V4 Flash',
  'deepseek v4 flash': 'DeepSeek V4 Flash',
  qwen36flash: 'Qwen 3.6 Flash',
  qwen: 'Qwen 3.6 Flash',
  'qwen 3.6 flash': 'Qwen 3.6 Flash',
  '千问': 'Qwen 3.6 Flash',
  '千问3.6flash': 'Qwen 3.6 Flash',
  // Keep the backend handle and share URL stable; this is only the current
  // user-facing label for the agent behind that endpoint.
  glm53flash: 'GPT-5 nano',
  'glm5.3flash': 'GPT-5 nano',
  glm: 'GPT-5 nano',
  'glm 5.3 flash': 'GPT-5 nano',
}

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[\u2010-\u2015_]+/g, ' ').replace(/\s+/g, ' ')
}

/** Convert internal handles and legacy labels into the user-facing model name. */
export function standardModelName(value: string): string {
  return STANDARD_NAMES[normalized(value)] ?? value
}

export function standardAgentName(handle: string, displayName: string): string {
  return standardModelName(handle) !== handle ? standardModelName(handle) : standardModelName(displayName)
}
