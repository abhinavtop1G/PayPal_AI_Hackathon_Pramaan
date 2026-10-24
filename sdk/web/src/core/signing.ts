/**
 * Request signing, as the gateway checks it (backend/security.py): `X-Signature: sha256=<hex HMAC-SHA256(secret,
 * "<unix seconds>.<raw body>")>` with `X-Timestamp`. The gateway accepts a signature once, within 5 minutes.
 *
 * Sign on your server, never in a browser or app: whoever holds the secret can sign requests.
 */

const enc = new TextEncoder();

function subtle(): SubtleCrypto {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (!c?.subtle) throw new Error("WebCrypto is not available (needs a secure context or Node 18+)");
  return c.subtle;
}

const hex = (b: ArrayBuffer) => Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");

export async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const key = await subtle().importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await subtle().sign("HMAC", key, enc.encode(message)));
}

/** Headers for a signed request; `body` must be the exact string sent. */
export async function signRequest(secret: string, body: string, unixSeconds = Math.floor(Date.now() / 1000)):
  Promise<{ "X-Timestamp": string; "X-Signature": string }> {
  const ts = String(unixSeconds);
  return { "X-Timestamp": ts, "X-Signature": `sha256=${await hmacSha256Hex(secret, `${ts}.${body}`)}` };
}
