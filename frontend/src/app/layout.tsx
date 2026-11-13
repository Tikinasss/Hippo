import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const plex = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-plex" });

export const metadata: Metadata = {
  title: "Hippo – Écoconception des parcours de soins",
  description: "Assistant d'écoconception des parcours de soins : impact carbone, alternatives sourcées, plan d'action HAS.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className={plex.variable}>{children}</body>
    </html>
  );
}
