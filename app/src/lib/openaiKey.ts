const STORAGE_KEY = "tf_openai_key";

export function getStoredOpenAIKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(STORAGE_KEY);
}

export function setStoredOpenAIKey(key: string): void {
  localStorage.setItem(STORAGE_KEY, key);
}

export function clearStoredOpenAIKey(): void {
  localStorage.removeItem(STORAGE_KEY);
}
