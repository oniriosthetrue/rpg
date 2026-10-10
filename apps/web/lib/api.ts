// Helpers serveur pour parler au backend `api` en HTTP interne.
// La clé X-API-Key est injectée ICI (côté serveur Next), jamais dans le navigateur.

const API = process.env.API_INTERNAL_URL ?? "http://api:8000";
const CLE = process.env.DND_API_KEY ?? "";

export function enTetes(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (CLE) h["X-API-Key"] = CLE;
  return h;
}

export function url(chemin: string): string {
  return `${API}${chemin}`;
}
