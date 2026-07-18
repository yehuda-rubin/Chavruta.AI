import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Chavruta.AI · בית מדרש",
  description:
    "Grounded Q&A, commentator explanation, and lesson preparation over the Jewish bookshelf — every answer cited to a retrieved source.",
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
