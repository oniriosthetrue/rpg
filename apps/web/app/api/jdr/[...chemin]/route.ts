import { NextRequest } from "next/server";
import { enTetes, url } from "@/lib/api";

// Requête JSON générique vers le backend. La clé X-API-Key est injectée ici
// (côté serveur Next), jamais dans le navigateur. GET/POST/PATCH/DELETE.

type Ctx = { params: { chemin: string[] } };

async function relais(req: NextRequest, method: string, ctx: Ctx) {
  const q = req.nextUrl.search;
  const corps =
    method === "GET" || method === "DELETE"
      ? undefined
      : await req.text();
  const reponse = await fetch(url(`/api/${ctx.params.chemin.join("/")}${q}`), {
    method,
    headers: enTetes(),
    cache: "no-store",
    body: corps,
  });
  const texte = await reponse.text();
  return new Response(texte, {
    status: reponse.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return relais(req, "GET", ctx);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  return relais(req, "POST", ctx);
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  return relais(req, "PATCH", ctx);
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  return relais(req, "DELETE", ctx);
}
