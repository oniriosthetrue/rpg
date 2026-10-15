import { NextRequest, NextResponse } from "next/server";
import { url } from "@/lib/api";
import { COOKIE_SESSION } from "@/lib/session";

// Relais des routes d'authentification vers le backend. C'est ICI (côté
// navigateur/Next) que le jeton de session est placé dans un cookie httpOnly,
// jamais exposé au JS. Le backend, interne, renvoie le jeton dans le JSON ;
// on le retire du corps renvoyé au navigateur et on le stocke en cookie.

const DUREE_COOKIE = 60 * 60 * 24 * 30; // 30 jours (aligné sur SESSION_DUREE_S).

function cookieSession(valeur: string): string {
  return `${COOKIE_SESSION}=${valeur}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${DUREE_COOKIE}`;
}

const cookieEfface = `${COOKIE_SESSION}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;

async function relais(req: NextRequest, chemin: string[]): Promise<NextResponse> {
  const corps = await req.text();
  const jetonSession = req.cookies.get(COOKIE_SESSION)?.value;
  const reponse = await fetch(url(`/api/auth/${chemin.join("/")}`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // Certaines routes auth sont protégées (ex. /delete) : on relaie la session.
      ...(jetonSession ? { "X-Session": jetonSession } : {}),
    },
    body: corps,
    cache: "no-store",
  });

  const statut = reponse.status;
  const texte = await reponse.text();
  let json: Record<string, unknown>;
  try {
    json = JSON.parse(texte);
  } catch {
    return new NextResponse(texte, {
      status: statut,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }

  const sortie = new NextResponse(JSON.stringify(json), {
    status: statut,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

  const action = json.type;
  const session = json.session;
  if (action === "connecte" && typeof session === "string") {
    delete json.session; // ne jamais renvoyer le jeton au JS du navigateur
    const avecCookie = new NextResponse(JSON.stringify(json), {
      status: statut,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
    avecCookie.headers.append("Set-Cookie", cookieSession(session));
    return avecCookie;
  }
  if (action === "deconnecte" || action === "supprime") {
    sortie.headers.append("Set-Cookie", cookieEfface);
  }
  return sortie;
}

type Ctx = { params: Promise<{ chemin: string[] }> };

export async function POST(req: NextRequest, ctx: Ctx) {
  const { chemin } = await ctx.params;
  return relais(req, chemin);
}

// GET /api/auth/me — renvoie le compte courant (relais avec la session).
export async function GET(req: NextRequest, ctx: Ctx) {
  const { chemin } = await ctx.params;
  const session = req.cookies.get(COOKIE_SESSION)?.value;
  const reponse = await fetch(url(`/api/auth/${chemin.join("/")}`), {
    method: "GET",
    headers: session ? { "X-Session": session } : {},
    cache: "no-store",
  });
  const texte = await reponse.text();
  return new NextResponse(texte, {
    status: reponse.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
