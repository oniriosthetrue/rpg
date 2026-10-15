import { NextRequest } from "next/server";
import { enTetes, sessionDe, url } from "@/lib/api";

// Relaye la requête de chat vers le backend et renvoie le flux SSE tel quel.
// Le navigateur ne voit jamais la clé X-API-Key (injectée ici côté serveur).
export async function POST(req: NextRequest) {
  const corps = await req.json();
  // `signal: req.signal` propage l'annulation du navigateur (bouton Stop) vers
  // le backend : la connexion proxy<->api se ferme, et `request.is_disconnected()`
  // devient vrai côté FastAPI pour interrompre le run et libérer le GPU.
  const reponse = await fetch(url("/api/chat"), {
    method: "POST",
    headers: enTetes(sessionDe(req)),
    body: JSON.stringify(corps),
    signal: req.signal,
  });

  return new Response(reponse.body, {
    status: reponse.status,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
