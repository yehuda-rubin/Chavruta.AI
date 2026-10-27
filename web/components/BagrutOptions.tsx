import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";

export interface BagrutFields {
  subject: string;
  track: string;
  units: string;
  action: string;
}

// Bagrut-mode controls (subject · track · units · action). Track shows when subject is "" or "tanakh".
// Rendered only when intent === "bagrut".
export function BagrutOptions({
  lang,
  value,
  onChange,
}: {
  lang: Lang;
  value: BagrutFields;
  onChange: (v: BagrutFields) => void;
}) {
  const set = (patch: Partial<BagrutFields>) => onChange({ ...value, ...patch });
  const sel = "rounded-full bg-white/70 px-3 py-1 outline-none cursor-pointer";
  const showTrack = value.subject === "" || value.subject === "tanakh";
  return (
    <div className="px-7 py-2 flex items-center gap-2 flex-wrap border-b border-white/40 bg-white/30 text-xs">
      <span className="text-ink/50 font-semibold">{tr(lang, "bagrutSubjectLabel")}:</span>
      <select
        className={sel}
        value={value.subject}
        onChange={(e) => {
          const nextSubj = e.target.value;
          set({
            subject: nextSubj,
            track: nextSubj === "" || nextSubj === "tanakh" ? value.track : "",
          });
        }}
      >
        <option value="">{tr(lang, "bagrutSubjAuto")}</option>
        <option value="tanakh">{tr(lang, "bagrutSubjTanakh")}</option>
        <option value="gemara">{tr(lang, "bagrutSubjGemara")}</option>
        <option value="toshba">{tr(lang, "bagrutSubjToshba")}</option>
      </select>
      {showTrack && (
        <>
          <span className="text-ink/50 font-semibold ms-2">{tr(lang, "bagrutTrackLabel")}:</span>
          <select className={sel} value={value.track} onChange={(e) => set({ track: e.target.value })}>
            <option value="">{tr(lang, "bagrutTrackAuto")}</option>
            <option value="mmd">{tr(lang, "bagrutTrackMmd")}</option>
            <option value="mamlachti">{tr(lang, "bagrutTrackMamlachti")}</option>
          </select>
        </>
      )}
      <span className="text-ink/50 font-semibold ms-2">{tr(lang, "bagrutUnitsLabel")}:</span>
      <select className={sel} value={value.units} onChange={(e) => set({ units: e.target.value })}>
        <option value="">{tr(lang, "bagrutUnitsAuto")}</option>
        <option value="2">{tr(lang, "bagrutUnits2")}</option>
        <option value="3">{tr(lang, "bagrutUnits3")}</option>
        <option value="5">{tr(lang, "bagrutUnits5")}</option>
      </select>
      <span className="text-ink/50 font-semibold ms-2">{tr(lang, "bagrutActionLabel")}:</span>
      <select className={sel} value={value.action} onChange={(e) => set({ action: e.target.value })}>
        <option value="practice">{tr(lang, "bagrutActPractice")}</option>
        <option value="check">{tr(lang, "bagrutActCheck")}</option>
        <option value="summary">{tr(lang, "bagrutActSummary")}</option>
        <option value="exam">{tr(lang, "bagrutActExam")}</option>
        <option value="solution">{lang === "he" ? "פתרון שאלון בגרות (קובץ)" : "Exam Solution (File)"}</option>
      </select>
    </div>
  );
}
