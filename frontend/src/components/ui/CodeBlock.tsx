"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

type Lang = "ts" | "kotlin" | "bash" | "json" | "python" | "text";

const KEYWORDS: Record<Lang, string[]> = {
  ts: ["import", "from", "export", "const", "let", "await", "async", "new", "return", "if", "else", "function", "type", "interface", "true", "false", "null", "undefined"],
  kotlin: ["import", "val", "var", "fun", "class", "object", "override", "return", "if", "else", "when", "true", "false", "null", "private", "companion"],
  bash: ["curl", "export", "npm", "pip", "python", "uvicorn", "cd", "gradle"],
  json: ["true", "false", "null"],
  python: ["import", "from", "def", "return", "if", "else", "True", "False", "None", "with", "as"],
  text: [],
};

/** Tiny tokenizer: comments, strings, numbers, keywords. Enough for docs-sized snippets, no dependency. */
function highlight(code: string, lang: Lang): React.ReactNode[] {
  if (lang === "text") return [code];
  const kw = KEYWORDS[lang];
  const comment = lang === "bash" || lang === "python" ? "#[^\\n]*" : "//[^\\n]*";
  const re = new RegExp(`(${comment})|("(?:[^"\\\\\\n]|\\\\.)*"|'(?:[^'\\\\\\n]|\\\\.)*'|\`[^\`]*\`)|\\b(\\d+(?:\\.\\d+)?)\\b|\\b(${kw.join("|") || "$^"})\\b`, "g");
  const out: React.ReactNode[] = [];
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(code))) {
    if (m.index > last) out.push(code.slice(last, m.index));
    const cls = m[1] ? "text-label-tertiary italic" : m[2] ? (lang === "json" && code[re.lastIndex] === ":" ? "text-[#9ec5f4]" : "text-[#7ee2a8]")
      : m[3] ? "text-[#ffb86b]" : "text-[#c4b5fd]";
    out.push(<span key={i++} className={cls}>{m[0]}</span>);
    last = re.lastIndex;
  }
  if (last < code.length) out.push(code.slice(last));
  return out;
}

/** A code sample with a language tag and a copy button. */
export function CodeBlock({ code, lang = "ts", title, className = "", maxHeight }: {
  code: string;
  lang?: Lang;
  title?: string;
  className?: string;
  maxHeight?: string;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {}
  };
  return (
    <div className={`squircle min-w-0 max-w-full overflow-hidden rounded-[var(--radius-card)] bg-[#0b0b0d] ring-1 ring-white/[0.07] ${className}`}>
      <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3.5 py-2">
        <span className="font-mono text-caption-2 uppercase tracking-[0.08em] text-label-tertiary">{title ?? lang}</span>
        <button onClick={copy} className="flex items-center gap-1 rounded-full px-2 py-0.5 text-caption-1 text-label-secondary hover:bg-fill-quaternary hover:text-label"
          aria-label="Copy code">
          {copied ? <Check className="size-3.5 text-sys-green" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre tabIndex={0} aria-label={title ?? lang} className="overflow-auto p-3.5 font-mono text-[0.78rem] leading-[1.6] text-label focus-visible:outline-offset-[-2px]" style={{ maxHeight }}>
        <code>{highlight(code, lang)}</code>
      </pre>
    </div>
  );
}
