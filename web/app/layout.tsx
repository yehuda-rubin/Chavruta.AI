import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "חברותא AI · בית מדרש",
  description:
    "שותפה ללימוד תורה — שאלה, הסבר ובניית שיעורים מעל המדף היהודי, עם מקורות מצוטטים.",
  applicationName: "חברותא AI",
  appleWebApp: { capable: true, title: "חברותא", statusBarStyle: "default" },
  formatDetection: { telephone: false },
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
      </body>
    </html>
  );
}
