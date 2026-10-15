"""Authentification par compte (email + mot de passe) pour MJ D&D.

Trois modules :
- `security` : hachage des mots de passe (PBKDF2, stdlib) et jetons de session
  signés (HMAC, stdlib) — aucune dépendance externe, pour un build slim fiable ;
- `store` : persistance des comptes dans un fichier SQLite (volume dédié) ;
- `scope` : isolation des données de jeu par utilisateur (répertoires dédiés) ;
- `mailer` : envoi des liens de vérification / réinitialisation (SMTP ou console).
"""
