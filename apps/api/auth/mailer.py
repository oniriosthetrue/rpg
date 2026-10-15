"""Envoi des emails de vérification et de réinitialisation.

SMTP via la bibliothèque standard (`smtplib`/`email`). Si SMTP n'est pas
configuré (pas de `SMTP_HOST`), on bascule en **mode console** : le lien est
journalisé (et renvoyé à l'API en debug) au lieu d'être envoyé — pratique tant
qu'un fournisseur email n'est pas branché.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from settings import settings

log = logging.getLogger("mj.mailer")


def _smtp_configure() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def envoyer(destinataire: str, sujet: str, corps: str) -> bool:
    """Envoie un email. Retourne True si envoyé, False si mode console (loggé)."""
    if not _smtp_configure():
        log.info("[email·console] À %s — %s\n%s", destinataire, sujet, corps)
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(message)
        return True
    except Exception as exc:  # ne jamais casser une inscription à cause de l'envoi
        log.exception("Échec d'envoi d'email vers %s : %s", destinataire, exc)
        return False


def lien_verification(jeton: str) -> str:
    return f"{settings.base_url}/verifier?token={jeton}"


def lien_reinitialisation(jeton: str) -> str:
    return f"{settings.base_url}/reinitialiser?token={jeton}"


def envoyer_verification(email: str, jeton: str) -> bool:
    lien = lien_verification(jeton)
    return envoyer(
        email,
        "Confirme ton compte MJ D&D",
        "Bienvenue sur MJ D&D !\n\n"
        "Confirme ton adresse en ouvrant ce lien :\n\n"
        f"{lien}\n\n"
        "Si tu n'es pas à l'origine de cette inscription, ignore cet email.",
    )


def envoyer_reinitialisation(email: str, jeton: str) -> bool:
    lien = lien_reinitialisation(jeton)
    return envoyer(
        email,
        "Réinitialiser ton mot de passe MJ D&D",
        "Quelqu'un a demandé à réinitialiser ton mot de passe.\n\n"
        "Ouvre ce lien pour en choisir un nouveau :\n\n"
        f"{lien}\n\n"
        "Si ce n'est pas toi, ignore cet email.",
    )
