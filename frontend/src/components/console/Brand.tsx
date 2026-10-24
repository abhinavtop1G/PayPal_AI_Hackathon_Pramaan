import Link from "next/link";

/** The PRAMAAN mark: a shield whose check is drawn as a proof stroke, on the brand gradient. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <span className="squircle relative flex shrink-0 items-center justify-center rounded-[28%] bg-gradient-to-br from-[#5e5ce6] via-[#3f7cf0] to-[#38c6f0] shadow-[0_6px_20px_rgb(94_92_230/0.45),inset_0_1px_0_rgb(255_255_255/0.35)]"
      style={{ width: size, height: size }} aria-hidden>
      <svg viewBox="0 0 24 24" width={size * 0.6} height={size * 0.6} fill="none">
        <path d="M12 2.8 4.6 5.6v5.5c0 4.6 3.1 8.6 7.4 10.1 4.3-1.5 7.4-5.5 7.4-10.1V5.6L12 2.8Z" fill="rgb(255 255 255 / 0.16)" stroke="#fff" strokeWidth={1.6} strokeLinejoin="round" />
        <path d="m8.4 12.2 2.5 2.5 4.9-5.2" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function Wordmark({ href = "/", sub }: { href?: string; sub?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2.5 rounded-xl text-label" title="PRAMAAN home">
      <Logo />
      <span className="leading-tight">
        <span className="block text-headline tracking-[0.06em]">PRAMAAN</span>
        {sub && <span className="block text-caption-2 text-label-tertiary">{sub}</span>}
      </span>
    </Link>
  );
}
