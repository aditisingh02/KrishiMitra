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
  title: "KrishiMitra - Agentic Agronomy OS",
  description:
    "A multilingual AI agronomist that diagnoses crops, predicts risk, and guides natural farming.",
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
