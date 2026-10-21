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
    // Corps illisible (ex. page HTML d'erreur, réponse vide). Sur un statut
    // HTTP d'échec, on lève une erreur explicite plutôt que de renvoyer
    // `undefined` (qui ferait planter les composants à la lecture de `.length`).
    if (!reponse.ok) {
      throw new ErreurJdr(
        reponse.status === 401
          ? "Session expirée. Reconnecte-toi."
          : `Erreur serveur (${reponse.status}).`,
        reponse.status === 401 ? "non_autorise" : "erreur",
      );
    }
    throw new ErreurJdr(
      `Réponse invalide du serveur (${reponse.status}).`,
    );
  }
  // Statut HTTP d'échec : on lève toujours, même si le corps ne porte pas
  // `ok:false` (ex. le proxy renvoie `{ detail: ... }` sur un 401/403/500).
  if (!reponse.ok) {
    throw new ErreurJdr(
      String(
        json.erreur ??
          json.message ??
          json.detail ??
          (reponse.status === 401
            ? "Session expirée. Reconnecte-toi."
            : `Erreur serveur (${reponse.status}).`),
      ),
      String(json.type ?? (reponse.status === 401 ? "non_autorise" : "erreur")),
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
