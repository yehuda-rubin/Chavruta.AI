import Link from "next/link";

export const metadata = { title: "לא נמצא · חברותא AI" };

// Branded 404 (replaces Next's default). Owns its scroll — the app body is overflow-hidden.
export default function NotFound() {
  return (
    <div dir="rtl" className="h-screen overflow-y-auto grid place-items-center p-6">
      <div className="glass rounded-[28px] p-10 w-full max-w-sm text-center flex flex-col gap-4">
        <div className="h-16 w-16 mx-auto rounded-3xl grad grid place-items-center text-white font-serif text-3xl font-black shadow-lg shadow-tekhelet/20">
          ח
        </div>
        <h1 className="font-serif text-2xl font-bold text-tekhelet">הדף לא נמצא</h1>
        <p className="text-sm text-ink/60 leading-relaxed">העמוד שחיפשת אינו קיים או הוסר.</p>
        <Link
          href="/"
          className="mt-1 py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition"
        >
          חזרה לחברותא
        </Link>
      </div>
    </div>
  );
}
