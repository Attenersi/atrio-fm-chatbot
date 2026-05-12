import "./globals.css";
import type { Metadata } from "next";
import { I18nProvider } from "../i18n/I18nProvider";

export const metadata: Metadata = {
  title: "Atrio FM Assistant",
  description: "Facility Management assistant with RAG",
  icons: {
    icon: [
      {
        url: "/atrio-brand-assets/favicon.ico?v=4",
        sizes: "48x48",
        type: "image/x-icon",
      },
      {
        url: "/atrio-brand-assets/favicon.png?v=4",
        sizes: "32x32",
        type: "image/png",
      },
      {
        url: "/atrio-brand-assets/atrio-icon-32.png?v=4",
        sizes: "32x32",
        type: "image/png",
      },
      {
        url: "/atrio-brand-assets/atrio-icon-192.png?v=4",
        sizes: "192x192",
        type: "image/png",
      },
      {
        url: "/atrio-brand-assets/atrio-icon-512.png?v=4",
        sizes: "512x512",
        type: "image/png",
      },
    ],
    apple: [
      {
        url: "/atrio-brand-assets/apple-touch-icon.png?v=4",
        sizes: "180x180",
        type: "image/png",
      },
    ],
    shortcut: ["/atrio-brand-assets/favicon.ico?v=4"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
