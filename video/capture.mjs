// Capture 1920x1080 screenshots of the PRAMAAN console via the Chrome DevTools Protocol (real-time waits, so API calls finish).
//   node capture.mjs            (console on http://localhost:3000, API on :8000)
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const OUT = new URL("./assets/shots/", import.meta.url);
const SHOTS = [
  ["shot_routine_allow", "scenario=genuine_routine"],
  ["shot_simswap_block", "scenario=sim_swap"],
  ["shot_newphone_passkey", "scenario=genuine_new_phone"],
  ["shot_newphone_passed", "scenario=genuine_new_phone&verify=pass"],
  ["shot_coerced_callback", "scenario=coerced"],
  ["shot_bot_block", "scenario=bot"],
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${process.env.TEMP}/pramaan-capture-prof`, "--window-size=1920,1080", "about:blank"], { stdio: "ignore" });

let targets;
for (let i = 0; i < 50 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); } catch { await sleep(200); }
}
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((r) => { const n = ++id; pending.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });

await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
mkdirSync(OUT, { recursive: true });
for (const [name, q] of SHOTS) {
  await send("Page.navigate", { url: `http://localhost:3000/?${q}` });
  await sleep(4500);
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(new URL(`${name}.png`, OUT), Buffer.from(r.result.data, "base64"));
  console.log("captured", name);
}
ws.close();
chrome.kill();
