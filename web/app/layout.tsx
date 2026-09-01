import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { AccessibilityWidget } from "@/components/AccessibilityWidget";

const SITE_URL = "https://chavrutaai.org";
const SITE_TITLE = "חברותא AI · בית מדרש";
const SITE_DESCRIPTION =
  "שותף ללימוד תורה — שאלה, הסבר ובניית שיעורים מעל המדף היהודי, עם מקורות מצוטטים.";

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "חברותא AI",
  alternateName: "Chavruta.AI",
  url: SITE_URL,
  description: SITE_DESCRIPTION,
  applicationCategory: "EducationalApplication",
  operatingSystem: "All",
  inLanguage: ["he", "en"],
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "ILS",
  },
};

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
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      {/* h-dvh (dynamic viewport height), not h-screen (100vh): on mobile Chrome, 100vh assumes the
          address bar is hidden, so whenever it's actually showing (very common right after
          navigating between chats), content anchored to a 100vh container overflows past the real
          visible area and gets clipped — caught live 2026-08-07 as the header vanishing on mobile. */}
      <body className="font-sans text-ink h-dvh overflow-hidden">
        <noscript>
          <div style={{ padding: "2rem", fontFamily: "sans-serif", maxWidth: "800px", margin: "0 auto" }}>
            <h1>חברותא AI · בית מדרש</h1>
            <p>שותף ללימוד תורה — שאלה, הסבר ובניית שיעורים מעל המדף היהודי, עם מקורות מצוטטים.</p>
            <p>מערכת חברותא AI מאפשרת לימוד מבוסס מקורות אותנטיים: תנ״ך, תלמוד בבלי וירושלמי, רמב״ם, שולחן ערוך, מפרשים וספרי הלכה.</p>
            <ul>
              <li><strong>שאילתא:</strong> מענה לשאלות לימודיות והלכתיות עם מראה מקום מדויק.</li>
              <li><strong>הסבר מעמיק:</strong> ביאור מהלכים וסוגיות שלב אחרי שלב.</li>
              <li><strong>בניית שיעור:</strong> עריכת מערכי שיעור ודפי מקורות מותאמים.</li>
            </ul>
            <p>
              <a href="/llms.txt">מידע מורחב למודלי שפה (llms.txt)</a> | <a href="/terms">תנאי שימוש</a> | <a href="/privacy">מדיניות פרטיות</a> | <a href="/limits">מכסות ותוכניות</a>
            </p>
          </div>
        </noscript>
        {/* Inert unless Supabase env is set — then it gates the app behind sign-in. */}
        <AuthProvider>{children}</AuthProvider>
        <AccessibilityWidget />
      </body>
    </html>
  );
}
