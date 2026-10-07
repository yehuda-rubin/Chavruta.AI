import type { Metadata } from "next";
import { Landing } from "@/components/Landing";

// The public front door. "/" shows this to signed-out visitors; /welcome is the same page at a stable
// address that never redirects, so it can be linked, previewed and indexed regardless of session.
export const metadata: Metadata = { alternates: { canonical: "/" } };

export default function Welcome() {
  return <Landing />;
}
