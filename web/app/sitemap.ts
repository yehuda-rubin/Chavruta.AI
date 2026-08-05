import type { MetadataRoute } from "next";

const SITE_URL = "https://chavruta.duckdns.org";

// Only the routes meant for public discovery. /reset-password is a utility page
// reached from an email link, not something anyone should find via search.
const ROUTES = ["", "/privacy", "/terms", "/accessibility", "/limits"];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ROUTES.map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified: now,
  }));
}
