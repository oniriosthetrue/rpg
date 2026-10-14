import { createHash, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

function empreinte(value: string) {
  return createHash("sha256").update(value, "utf8").digest();
}

function correspond(value: string, expected: string) {
  return timingSafeEqual(empreinte(value), empreinte(expected));
}

function identifiantsValides(header: string | null, username: string, password: string) {
  if (!header?.startsWith("Basic ")) return false;

  const encoded = header.slice(6);
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) return false;

  const decoded = Buffer.from(encoded, "base64");
  if (decoded.toString("base64") !== encoded) return false;

  const credentials = decoded.toString("utf8");
  const separator = credentials.indexOf(":");
  if (separator < 1) return false;

  const usernameMatches = correspond(credentials.slice(0, separator), username);
  const passwordMatches = correspond(credentials.slice(separator + 1), password);
  return usernameMatches && passwordMatches;
}

export function proxy(request: NextRequest) {
  const username = process.env.WEB_AUTH_USERNAME?.trim();
  const password = process.env.WEB_AUTH_PASSWORD;

  if (!username || !password) {
    return new NextResponse("Authentification non configurée.", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }

  if (identifiantsValides(request.headers.get("authorization"), username, password)) {
    return NextResponse.next();
  }

  return new NextResponse("Authentification requise.", {
    status: 401,
    headers: {
      "Cache-Control": "no-store",
      "WWW-Authenticate": 'Basic realm="MJ D&D", charset="UTF-8"',
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
