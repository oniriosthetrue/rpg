import { NextRequest } from "next/server";
import { enTetes, url } from "@/lib/api";

// Requête JSON générique vers le backend (lecture seule : GET).
export async function GET(
  req: NextRequest,
  { params }: { params: { chemin: string[] } },
) {
  const q = req.nextUrl.search;
  const reponse = await fetch(url(`/api/${params.chemin.join("/")}${q}`), {
    method: "GET",
    headers: enTetes(),
    cache: "no-store",
  });
  const corps = await reponse.text();
  return new Response(corps, {
    status: reponse.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
