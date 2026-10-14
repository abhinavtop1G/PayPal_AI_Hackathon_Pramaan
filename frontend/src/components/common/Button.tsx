"use client";

/**
 * Buttons respond on pointer-down: a quick scale to 0.97 while pressed, released on a spring-like ease.
 * `tint` maps to a system colour; `variant` follows iOS: filled, tinted (colour at low opacity) or plain gray.
 */
type Tint = "blue" | "red" | "green" | "gray";
const FILLED: Record<Tint, string> = {
  blue: "bg-sys-blue text-white",
  red: "bg-sys-red text-white",
  green: "bg-sys-green text-black",
  gray: "bg-fill text-label",
};
const TINTED: Record<Tint, string> = {
  blue: "bg-sys-blue/15 text-sys-blue",
  red: "bg-sys-red/15 text-sys-red",
  green: "bg-sys-green/15 text-sys-green",
  gray: "bg-fill-tertiary text-label",
};

export function Button({
  tint = "blue",
  variant = "filled",
  size = "large",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  tint?: Tint;
  variant?: "filled" | "tinted";
  size?: "large" | "small";
}) {
  const s = size === "large" ? "h-[3.125rem] rounded-[0.875rem] px-5 text-headline" : "h-8 rounded-full px-3.5 text-footnote font-semibold";
  return (
    <button
      {...props}
      className={`squircle inline-flex items-center justify-center gap-2 transition-[scale,opacity,background-color] duration-200 ease-[cubic-bezier(0.25,1,0.5,1)] active:scale-[0.97] active:duration-75 disabled:opacity-40 ${s} ${
        variant === "filled" ? FILLED[tint] : TINTED[tint]
      } ${className}`}
    />
  );
}

/** Round icon button for toolbars (play, restart). */
export function IconButton({
  label,
  className = "",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className={`flex size-9 items-center justify-center rounded-full bg-fill-tertiary text-label transition-[scale,background-color] duration-200 hover:bg-fill-secondary active:scale-[0.92] active:duration-75 ${className}`}
    >
      {children}
    </button>
  );
}
