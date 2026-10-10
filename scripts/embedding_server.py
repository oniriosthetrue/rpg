#!/usr/bin/env python3
"""
Serveur d'embeddings minimal (OpenAI-compatible) pour Open-WebUI.

Choix : sentence-transformers + http.server (stdlib), PAS TEI.
Raison : le backend CPU de TEI (candle) boucle à l'infini au warmup sur ce CPU
(AMD EPYC Rome SANS AVX-512 : les kernels bf16/fp16 de candle sont émulés en
logiciel et ne se terminent pas). sentence-transformers (ONNX/AVX2) fonctionne.

Expose :
  GET  /health        -> {"status":"ok"} (200) dès que le modèle est chargé, 503 sinon
  POST /v1/embeddings -> format OpenAI / OpenAI-compatible (input: str | [str])
  GET  /v1/models     -> liste le modèle servi

Variables d'env :
  EMBED_MODEL_NAME  nom du modèle HF (défaut Qwen/Qwen3-Embedding-0.6B)
  EMBED_PORT        port d'écoute (défaut 8080)
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
PORT = int(os.environ.get("EMBED_PORT", "8080"))

# Sémaphore simple : le modèle n'est prêt qu'après la fin du chargement.
_ready = threading.Event()
_model = None
_load_error = None


def _load_model():
    global _model, _load_error
    try:
        from sentence_transformers import SentenceTransformer

        # Qwen3-Embedding nécessite le pooling "last token" + normalisation.
        # sentence-transformers lit modules.json / config.json du repo HF,
        # mais on force le trust_remote_code pour le pooling spécifique Qwen3.
        _model = SentenceTransformer(
            MODEL_NAME,
            trust_remote_code=True,
            model_kwargs={"dtype": "float32"},
        )
        _ready.set()
        print(f"[embedding] modèle chargé : {MODEL_NAME}", flush=True)
    except Exception as exc:  # noqa: BLE001
        _load_error = str(exc)
        print(f"[embedding] ERREUR de chargement : {exc}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "EmbeddingServer/1.0"
    # IMPORTANT : HTTP/1.1 pour le keep-alive. En HTTP/1.0 (le défaut de
    # BaseHTTPRequestHandler), le serveur ferme le socket après chaque réponse
    # sans envoyer "Connection: close" ; le client (aiohttp d'Open WebUI) croit
    # la connexion encore valide, y envoie la requête suivante, et reçoit
    # "Connection reset by peer" dès la 2e requête sur la même connexion.
    protocol_version = "HTTP/1.1"

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path in ("/health", "/healthz", "/health/ready"):
            if _ready.is_set():
                self._send_json(200, {"status": "ok", "model": MODEL_NAME})
            else:
                self._send_json(503, {"status": "loading"})
        elif self.path in ("/v1/models", "/models"):
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": MODEL_NAME,
                            "object": "model",
                            "owned_by": "local",
                        }
                    ],
                },
            )
        else:
            self._send_json(404, {"error": {"message": "not found", "type": "invalid_request"}})

    def do_POST(self):  # noqa: N802
        if self.path not in ("/v1/embeddings", "/embeddings"):
            self._send_json(404, {"error": {"message": "not found", "type": "invalid_request"}})
            return
        if not _ready.is_set():
            self._send_json(503, {"error": {"message": "model is loading", "type": "server_error"}})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            req = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:  # noqa: BLE001
            self._send_json(400, {"error": {"message": f"bad json: {exc}", "type": "invalid_request"}})
            return

        inp = req.get("input", req.get("inputs"))
        if inp is None:
            self._send_json(400, {"error": {"message": "'input' is required", "type": "invalid_request"}})
            return

        # OpenAI : input = str | [str] | [int] (tokens) — on gère str et liste de str.
        if isinstance(inp, str):
            texts = [inp]
            single = True
        elif isinstance(inp, list) and all(isinstance(x, str) for x in inp):
            texts = inp
            single = False
        else:
            self._send_json(400, {"error": {"message": "unsupported input type", "type": "invalid_request"}})
            return

        try:
            # encode() renvoie (n, dim) ; normalize_embeddings pour un usage cosine.
            vecs = _model.encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": {"message": f"encode error: {exc}", "type": "server_error"}})
            return

        if single:
            vecs = [vecs[0].tolist()]
        else:
            vecs = [v.tolist() for v in vecs]

        resp = {
            "object": "list",
            "model": req.get("model", MODEL_NAME),
            "data": [
                {"object": "embedding", "index": i, "embedding": v}
                for i, v in enumerate(vecs)
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0, "completion_tokens": 0},
        }
        self._send_json(200, resp)

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("[http] " + (fmt % args) + "\n")


def main():
    threading.Thread(target=_load_model, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[embedding] écoute sur 0.0.0.0:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
