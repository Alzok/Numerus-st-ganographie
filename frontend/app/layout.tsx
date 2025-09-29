import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Watermark Tool",
  description: "Intégrer ou extraire un message caché dans vos images.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
