import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { AccessibilityWidget } from "@/components/AccessibilityWidget";

const SITE_URL = "https://chavruta.duckdns.org";
const SITE_TITLE = "חברותא AI · בית מדרש";
const SITE_DESCRIPTION =
  "שותפה ללימוד תורה — שאלה, הסבר ובניית שיעורים מעל המדף היהודי, עם מקורות מצוטטים.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  applicationName: "חברותא AI",
  appleWebApp: { capable: true, title: "חברותא", statusBarStyle: "default" },
  formatDetection: { telephone: false },
  robots: { index: true, follow: true },
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    locale: "he_IL",
    url: SITE_URL,
    siteName: SITE_TITLE,
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: "summary",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,      // prevent iOS zoom-on-input-focus jank in the chat composer
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf7ef" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1626" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // lang/dir default to Hebrew-first RTL, matching the static UI. The client toggles them at runtime.
  return (
    <html lang="he" dir="rtl">
      <body className="font-sans text-ink h-screen overflow-hidden">
        {/* Inert unless Supabase env is set — then it gates the app behind sign-in. */}
        <AuthProvider>{children}</AuthProvider>
        <AccessibilityWidget />
      </body>
    </html>
  );
}
