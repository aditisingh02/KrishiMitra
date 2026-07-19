import type { Metadata } from "next";
import { Instrument_Serif, Hanken_Grotesk, JetBrains_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { I18nProvider } from "@/lib/i18n-runtime";
import "./globals.css";

const sans = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const serif = Instrument_Serif({
  subsets: ["latin"],
  weight: ["400"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "KrishiMitra — Your AI Farming Assistant",
  description:
    "Snap a photo to spot crop disease, get natural farming advice, weather alerts and mandi prices — in Hindi or English, made for Indian farmers.",
  openGraph: {
    title: "KrishiMitra - Your AI Farming Assistant",
    description:
      "Snap a photo to spot crop disease, get natural farming advice, weather alerts and mandi prices — in Hindi or English, made for Indian farmers.",
    siteName: "KrishiMitra",
    type: "website",
    images: [{ url: "/og.png", width: 1814, height: 1024, alt: "KrishiMitra — Your AI Farming Assistant" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "KrishiMitra - Your AI Farming Assistant",
    description:
      "Snap a photo to spot crop disease, get natural farming advice, weather alerts and mandi prices — in Hindi or English.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorPrimary: "#346538",
          colorText: "#1A1A18",
          colorBackground: "#FFFFFF",
          borderRadius: "6px",
          fontFamily: "var(--font-sans)",
        },
      }}
    >
      <html lang="en" className={`${sans.variable} ${serif.variable} ${mono.variable}`}>
        <body className="min-h-screen bg-paper text-ink antialiased">
          <I18nProvider>{children}</I18nProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
