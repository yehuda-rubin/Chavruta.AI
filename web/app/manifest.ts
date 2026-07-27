import type { MetadataRoute } from "next";

// Web App Manifest — makes Chavruta installable (add to home screen) on phones/tablets, which is how
// it'll often be used in class. Next serves this at /manifest.webmanifest and links it automatically.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "חברותא AI",
    short_name: "חברותא",
    description:
      "שותפה ללימוד תורה — שאלה, הסבר ובניית שיעורים מעל המדף היהודי, עם מקורות מצוטטים.",
    lang: "he",
    dir: "rtl",
    start_url: "/",
    display: "standalone",
    background_color: "#faf7ef",
    theme_color: "#002045",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
