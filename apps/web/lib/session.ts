// Gestion de la session côté Next : nom du cookie et vérification du jeton
// signé émis par le backend (`auth/security.py`, format `b64url(payload).b64url(sig)`).
//
// Le proxy (middleware) vérifie la signature du cookie pour décider d'autoriser
// ou non une requête, SANS appeler le backend (rapide, sans état). La clé
// `AUTH_SECRET` doit être identique à celle de l'API.

import { createHmac, timingSafeEqual } from "node:crypto";

export const COOKIE_SESSION = "mj_session";

function unb64url(texte: string): Buffer {
  return Buffer.from(texte, "base64url");
}

/**
 * Vérifie la signature + l'expiration d'un jeton de session.
 * Retourne l'identifiant de compte (`uid`) si valide, sinon null.
 */
export function identifiantSession(jeton: string | undefined | null): string | null {
  const secret = process.env.AUTH_SECRET?.trim();
  if (!jeton || !secret || !jeton.includes(".")) return null;

  const [corps, sig] = jeton.split(".");
  if (!corps || !sig) return null;

  const attendu = createHmac("sha256", secret).update(corps, "utf8").digest("base64url");
  const a = Buffer.from(attendu);
  const b = Buffer.from(sig);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;

  try {
    const charge = JSON.parse(unb64url(corps).toString("utf8"));
    if (typeof charge.exp === "number" && charge.exp * 1000 < Date.now()) return null;
    return typeof charge.uid === "string" ? charge.uid : null;
  } catch {
    return null;
  }
}
