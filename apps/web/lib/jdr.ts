// Client API typé pour le frontend. Passe par le proxy serveur
// `/api/jdr/...` (qui injecte la clé X-API-Key). Décode l'enveloppe v1
// `{ ok, v, type, ... }` et lève une erreur si `ok` est faux.

const BASE = "/api/jdr";

export class ErreurJdr extends Error {
  constructor(
    message: string,
    readonly type?: string,
  ) {
    super(message);
    this.name = "ErreurJdr";
  }
}

// Enveloppe v1 : toute réponse porte `ok` + `type`. On la décode ici.
async function dechiffrer<T>(reponse: Response): Promise<T> {
  let json: Record<string, unknown>;
  try {
    json = await reponse.json();
  } catch {
    throw new ErreurJdr(
      `Réponse invalide du serveur (${reponse.status}).`,
    );
  }
  if (json.ok === false) {
    throw new ErreurJdr(
      String(json.erreur ?? json.message ?? "Erreur inconnue."),
      String(json.type ?? "erreur"),
    );
  }
  return json as T;
}

async function appel<T>(
  methode: string,
  chemin: string,
  corps?: unknown,
): Promise<T> {
  const reponse = await fetch(`${BASE}${chemin}`, {
    method: methode,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  return dechiffrer<T>(reponse);
}

export const jdr = {
  get: <T>(chemin: string) => appel<T>("GET", chemin),
  post: <T>(chemin: string, corps?: unknown) =>
    appel<T>("POST", chemin, corps ?? {}),
  patch: <T>(chemin: string, corps: unknown) =>
    appel<T>("PATCH", chemin, corps),
  del: <T>(chemin: string) => appel<T>("DELETE", chemin),
};
