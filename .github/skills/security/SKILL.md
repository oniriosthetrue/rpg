---
name: security
description: "Review and fix security vulnerabilities in this repository. Use for security audits, exploitable vulnerability investigations, npm audit findings, dependency upgrades, authentication and authorization flaws, API exposure, and requests to remediate security issues."
user-invocable: true
---

# Security Review and Remediation

Use this skill to investigate and, when requested, fix security problems in the
MJ D&D application. Verify the current repository state; do not assume that a
previous audit or deployment still reflects the files in the worktree.

## Procedure

1. **Establish scope and state**
   - Check `git status` and inspect relevant code, manifests, lockfiles, runtime
     configuration, and deployment topology before editing.
   - Keep unrelated or pre-existing work intact. Never display secret values or
     copy them into logs, reports, tests, or source files.
   - For an explicit vulnerability review, use the security-review workflow
     first and report findings before making fixes.

2. **Audit dependencies**
   - Use the package manager declared by the project. For the web app, run
     `npm audit` from `apps/web`; ensure the lockfile matches `package.json`.
   - Inspect advisory details and reachable dependency paths. Do not run
     `npm audit fix --force` blindly: evaluate major-version migrations and
     update related framework, CSS/PostCSS configuration, and route handler
     APIs together.
   - Audit production dependencies separately where useful. Do not claim
     Python dependencies are clean unless an applicable audit was actually run.

3. **Review application trust boundaries**
   - Trace public ingress through reverse proxy, Next.js handlers, and FastAPI.
     The backend's `X-API-Key` is a service credential, not proof that a public
     caller is authorized.
   - Check every route that injects server credentials, including catch-all
     JSON proxies and streaming chat handlers. Verify authentication covers
     both page routes and API routes and fails closed when credentials are
     absent.
   - Check authorization separately from authentication where records or
     actions are user-specific. Identify shared-account limitations instead of
     implying per-user isolation.
   - Treat HTTP Basic credentials as safe only over HTTPS. Compare credentials
     without leaking their values and do not log `Authorization` headers.

4. **Remediate surgically**
   - Fix all in-scope, actionable findings with repository conventions and
     minimal changes. Add or update tests for the vulnerability and the
     intended denial/allow behavior.
   - If a meaningful design or compatibility choice is needed, ask before
     proceeding. Update directly relevant deployment and user documentation,
     including required environment variables.

5. **Verify**
   - Run the relevant dependency audit, tests, type/build checks, and
     `git diff --check`.
   - For container commands, call the container configuration tool first.
     Build and deploy this project's `api`/`web` services only; never start or
     modify the separate LLM stack.
   - After deployment, verify service health and exercise both unauthorized
     and authorized paths without printing credentials. Verify the public
     site's HTTPS behavior when it is exposed through the configured domain.
   - Report exactly what was checked, what passed, any remaining limitations,
     and whether deployment completed.

## MJ D&D security context

- The public site is `rpg.minervia.fr`, routed through Traefik to the Next.js
  service. FastAPI is intended to remain internal to the Docker network.
- The server-side helper `apps/web/lib/api.ts` injects `DND_API_KEY` when
  calling FastAPI. Never expose this key to the browser.
- The web app's shared HTTP Basic guard is implemented in `apps/web/proxy.ts`.
  `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` configure it; Compose currently
  falls back to the API key for the password when no dedicated value is set.
  Prefer a separate strong password in the ignored `.env` file.
- The web package manifest, lockfile, PostCSS/Tailwind setup, and
  `apps/web/app/api/jdr/[...chemin]/route.ts` must be reviewed together when
  upgrading Next.js or CSS tooling.
