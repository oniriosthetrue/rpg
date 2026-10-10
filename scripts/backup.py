"""Sauvegarde cohérente des fiches perso et d'un snapshot Qdrant."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_PERSO = RACINE / "data-perso"
PREFIXE_ARCHIVE = "mj-dnd-"

_CREER_SNAPSHOT = """
import json
import urllib.request
from settings import settings

url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}/snapshots"
with urllib.request.urlopen(urllib.request.Request(url, method="POST"), timeout=3600) as response:
    print(response.read().decode())
"""

_TELECHARGER_SNAPSHOT = """
import shutil
import sys
import urllib.parse
import urllib.request
from settings import settings

nom = urllib.parse.quote(sys.argv[1], safe="")
url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}/snapshots/{nom}"
with urllib.request.urlopen(url, timeout=3600) as response:
    shutil.copyfileobj(response, sys.stdout.buffer)
"""

_SUPPRIMER_SNAPSHOT = """
import sys
import urllib.parse
import urllib.request
from settings import settings

nom = urllib.parse.quote(sys.argv[1], safe="")
url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}/snapshots/{nom}"
with urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=60) as response:
    response.read()
"""


def _compose_python(code: str, *args: str, capture_output: bool = True, **kwargs):
    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            code,
            *args,
        ],
        cwd=RACINE,
        check=True,
        capture_output=capture_output,
        **kwargs,
    )


def _creer_snapshot() -> str:
    resultat = _compose_python(_CREER_SNAPSHOT)
    donnees = json.loads(resultat.stdout)
    nom = donnees.get("result", {}).get("name")
    if not nom or Path(nom).name != nom:
        raise RuntimeError(f"Nom de snapshot Qdrant inattendu : {nom!r}")
    return nom


def _nettoyer_anciennes_archives(destination: Path, retention_jours: int) -> None:
    seuil = datetime.now(timezone.utc) - timedelta(days=retention_jours)
    for archive in destination.glob(f"{PREFIXE_ARCHIVE}*.tar.gz"):
        if datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc) < seuil:
            archive.unlink()


def sauvegarder(destination: Path, retention_jours: int) -> Path:
    if not DOSSIER_PERSO.is_dir():
        raise FileNotFoundError(f"Dossier des personnages absent : {DOSSIER_PERSO}")
    if retention_jours < 1:
        raise ValueError("La rétention doit être d'au moins un jour.")

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    horodatage = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archive = destination / f"{PREFIXE_ARCHIVE}{horodatage}.tar.gz"
    snapshot_nom: str | None = None

    with tempfile.TemporaryDirectory(prefix=".mj-dnd-backup-", dir=destination) as temporaire:
        temporaire_path = Path(temporaire)
        snapshot_path = temporaire_path / "qdrant.snapshot"
        archive_temp = temporaire_path / archive.name
        try:
            snapshot_nom = _creer_snapshot()
            with snapshot_path.open("wb") as fichier:
                _compose_python(
                    _TELECHARGER_SNAPSHOT,
                    snapshot_nom,
                    capture_output=False,
                    stdout=fichier,
                )

            manifeste = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "qdrant_snapshot": snapshot_nom,
                "contents": ["data-perso/", f"qdrant/{snapshot_nom}"],
            }
            manifeste_path = temporaire_path / "manifest.json"
            manifeste_path.write_text(
                json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with tarfile.open(archive_temp, "w:gz") as tar:
                tar.add(DOSSIER_PERSO, arcname="data-perso")
                tar.add(snapshot_path, arcname=f"qdrant/{snapshot_nom}")
                tar.add(manifeste_path, arcname="manifest.json")
            archive_temp.chmod(0o600)
            os.replace(archive_temp, archive)
        finally:
            if snapshot_nom:
                try:
                    _compose_python(_SUPPRIMER_SNAPSHOT, snapshot_nom)
                except subprocess.CalledProcessError as exc:
                    print(
                        f"Attention : impossible de supprimer le snapshot temporaire "
                        f"{snapshot_nom} dans Qdrant : {exc}",
                        file=sys.stderr,
                    )

    _nettoyer_anciennes_archives(destination, retention_jours)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path(
            os.environ.get("DND_BACKUP_DIR", str(Path.home() / "backups" / "mj-dnd"))
        ),
    )
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args()

    try:
        archive = sauvegarder(args.destination, args.retention_days)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"Échec de la sauvegarde : {exc}", file=sys.stderr)
        return 1
    print(f"Sauvegarde créée : {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
