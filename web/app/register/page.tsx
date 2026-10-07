// Referral links are shared as /register?ref=<code> (see app/partner/page.tsx) — that path had no
// page behind it. It is the sign-up page; the query string (ref, mode) is read client-side.
export { default } from "../signup/page";
