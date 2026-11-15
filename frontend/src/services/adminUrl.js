// Open admin on the API origin so session cookies are first-party.
export function adminUrl() {
  return `${(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')}/admin`;
}
