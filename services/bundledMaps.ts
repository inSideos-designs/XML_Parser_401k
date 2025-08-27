import defaultMap from '../maps/defaultMap.json';
import optionsByPromptJson from '../maps/optionsByPrompt.json';
import type { Prompt, OptionsByPrompt } from '../types';

export function getBundledPrompts(): Prompt[] {
  // Sanitize keys and build Prompt[]
  const keyCounts = new Map<string, number>();
  return (defaultMap as any[]).map((entry) => {
    const promptText = String(entry.prompt || '');
    let baseKey = String(entry.linknames || '').trim() || `prompt_${Math.random().toString(36).slice(2,8)}`;
    baseKey = baseKey.replace(/[^a-zA-Z0-9_]/g, '_');
    if (/^[0-9]/.test(baseKey)) baseKey = '_' + baseKey;
    const c = keyCounts.get(baseKey) || 0;
    const finalKey = c > 0 ? `${baseKey}_${c+1}` : baseKey;
    keyCounts.set(baseKey, c + 1);
    return {
      key: finalKey,
      prompt: promptText,
      linknames: String(entry.linknames || ''),
      quick: String(entry.quick || ''),
    } as Prompt;
  });
}

export function getBundledOptions(): OptionsByPrompt {
  return optionsByPromptJson as OptionsByPrompt;
}

