/**
 * @pramaan/web-sdk/server: for your backend (Node 18+, Deno, Bun, edge runtimes). Holds the API key and signing
 * secret, forwards what the browser / app SDK collected, and reports challenge results.
 *
 *   import { PramaanClient } from "@pramaan/web-sdk/server";
 *   const pramaan = new PramaanClient({ baseUrl: process.env.PRAMAAN_URL!, apiKey: process.env.PRAMAAN_KEY,
 *                                       hmacSecret: process.env.PRAMAAN_SECRET });
 *   const decision = await pramaan.authenticate({ ...collected, user_id: session.userId });
 */
export { PramaanClient, PramaanError, newRequestId, type ClientOptions, type ErrorCode } from "./core/client";
export { signRequest, hmacSha256Hex } from "./core/signing";
export * from "./core/types";
export type { GestureFeatures } from "./core/gestures";
