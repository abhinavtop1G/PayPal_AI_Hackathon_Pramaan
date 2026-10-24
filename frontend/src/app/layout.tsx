import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Devanagari } from "next/font/google";
import { MotionProvider } from "@/components/common/MotionProvider";
import "./globals.css";

// SF Pro can't be redistributed, so Apple platforms get it via -apple-system and everyone else gets
// Inter with its optical-size axis, the closest open match to SF's Text/Display split.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  axes: ["opsz"],
  display: "swap",
});

// Hindi alert copy: Apple platforms use their own Devanagari face; everyone else gets Noto.
const deva = Noto_Sans_Devanagari({
  variable: "--font-deva",
  subsets: ["devanagari"],
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "PRAMAAN — Risk-based Transaction Authentication", template: "%s" },
  description: "Allow, challenge or block an online transaction from behaviour, device and transaction signals, and see why.",
  applicationName: "PRAMAAN",
  openGraph: {
    title: "PRAMAAN — proof it's really you, in 42 ms",
    description: "Behaviour, device and transaction signals in one model: allow, the right step-up, or block, with the signals behind every decision.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${deva.variable} dark h-full`}>
      <head>
        {/* The page is already dark; stop the Dark Reader extension from recolouring the system palette. */}
        <meta name="darkreader-lock" />
      </head>
      <body className="min-h-full">
        <MotionProvider>{children}</MotionProvider>
      </body>
    </html>
  );
}
