import type { Metadata } from "next";

// The token in the URL is a credential: keep the page out of search indexes and out of Referer headers.
export const metadata: Metadata = {
  title: "אישור הורה · Parental consent",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function ParentConsentLayout({ children }: { children: React.ReactNode }) {
  return children;
}
