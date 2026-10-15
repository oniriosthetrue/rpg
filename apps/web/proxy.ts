import { NextRequest, NextResponse } from "next/server";
import { COOKIE_SESSION, identifiantSession } from "@/lib/session";

// Middleware d'accès. L'authentification passe par un cookie de session signé
// (`mj_session`, émis par `/api/auth/login`). On vérifie la signature du
// cookie localement (sans appeler le backend) pour décider d'autoriser ou non.

// Chemins accessibles sans session (auth + health).
function estPublic(pathname: string): boolean {
  if (pathname === "/connexion" || pathname === "/inscription") return true;
  if (pathname === "/reinitialiser" || pathname === "/verifier") return true;
  if (pathname === "/api/auth" || pathname.startsWith("/api/auth/")) return true;
  return false;
}

function pageConnexion(request: NextRequest): NextResponse {
  // Pour les pages : redirection ; pour les API : 401 JSON.
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json(
      { ok: false, v: 1, type: "erreur", erreur: "Authentification requise." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }
  const url = new URL("/connexion", request.url);
  const retour = request.nextUrl.pathname + request.nextUrl.search;
  if (retour !== "/") url.searchParams.set("retour", retour);
  const reponse = NextResponse.redirect(url);
  reponse.headers.set("Cache-Control", "no-store");
  return reponse;
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (estPublic(pathname)) {
    return NextResponse.next();
  }

  const uid = identifiantSession(request.cookies.get(COOKIE_SESSION)?.value);
  if (!uid) {
    return pageConnexion(request);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
