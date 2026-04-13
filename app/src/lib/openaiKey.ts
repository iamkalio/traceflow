/** OpenAI API key for evals: stored only in the browser (localStorage), never sent to persist on the server. */

const STORAGE_KEY = "traceflow.openai_api_key";

export function getStoredOpenAIKey(): string | null {
  if (typeof window === "undefined") return null;
  const v = localStorage.getItem(STORAGE_KEY);
  return v && v.trim() ? v.trim() : null;
}

export function setStoredOpenAIKey(key: string): void {
  localStorage.setItem(STORAGE_KEY, key.trim());
}

export function clearStoredOpenAIKey(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function isOpenAIKeyConfigured(): boolean {
  return Boolean(getStoredOpenAIKey());
}
