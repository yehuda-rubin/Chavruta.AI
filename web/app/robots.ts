import type { MetadataRoute } from "next";

const SITE_URL = "https://chavruta.duckdns.org";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/reset-password"],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
