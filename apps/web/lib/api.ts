// Helpers serveur pour parler au backend `api` en HTTP interne.
// La clé X-API-Key est injectée ICI (côté serveur Next), jamais dans le navigateur.
// Le jeton de session (cookie httpOnly) est relayé à l'API via l'en-tête
// interne `X-Session` pour que chaque requête soit isolée sur le compte.

const API = process.env.API_INTERNAL_URL ?? "http://api:8000";
const CLE = process.env.DND_API_KEY ?? "";

export function enTetes(session?: string | null): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (CLE) h["X-API-Key"] = CLE;
  if (session) h["X-Session"] = session;
  return h;
}

// Extrait le jeton de session du cookie de la requête entrante.
export function sessionDe(req: {
  cookies: { get(name: string): { value: string } | undefined };
}): string | null {
  return req.cookies.get("mj_session")?.value ?? null;
}

export function url(chemin: string): string {
  return `${API}${chemin}`;
}
