/** OpenAI API key for evals: stored only in this browser tab (sessionStorage), never sent to persist on the server. */

const STORAGE_KEY = "traceflow.openai_api_key";

export function getStoredOpenAIKey(): string | null {
  if (typeof window === "undefined") return null;
  const v = sessionStorage.getItem(STORAGE_KEY);
  return v && v.trim() ? v.trim() : null;
}

export function setStoredOpenAIKey(key: string): void {
  sessionStorage.setItem(STORAGE_KEY, key.trim());
}

export function clearStoredOpenAIKey(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}

export function isOpenAIKeyConfigured(): boolean {
  return Boolean(getStoredOpenAIKey());
}
