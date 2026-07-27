import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";

export interface LessonFields {
  audience: string;
  gradeBand: string;
  length: string;
}

// Lesson-mode controls (audience · grade band · length). Grade band shows only for a school
// audience, matching the static UI. Rendered only when intent === "lesson".
export function LessonOptions({
  lang,
  value,
  onChange,
}: {
  lang: Lang;
  value: LessonFields;
  onChange: (v: LessonFields) => void;
}) {
  const set = (patch: Partial<LessonFields>) => onChange({ ...value, ...patch });
  const sel = "rounded-full bg-white/70 px-3 py-1 outline-none cursor-pointer";
  return (
    <div className="px-7 py-2 flex items-center gap-2 flex-wrap border-b border-white/40 bg-white/30 text-xs">
      <span className="text-ink/50 font-semibold">{tr(lang, "forWhom")}</span>
      <select
        className={sel}
        value={value.audience}
        onChange={(e) => set({ audience: e.target.value, gradeBand: e.target.value === "school" ? value.gradeBand : "" })}
      >
        <option value="">{tr(lang, "audAuto")}</option>
        <option value="yeshiva">{tr(lang, "audYeshiva")}</option>
        <option value="school">{tr(lang, "audSchool")}</option>
      </select>
      {value.audience === "school" && (
        <select className={sel} value={value.gradeBand} onChange={(e) => set({ gradeBand: e.target.value })}>
          <option value="">{tr(lang, "bandAuto")}</option>
          <option value="a-c">{tr(lang, "band1")}</option>
          <option value="d-f">{tr(lang, "band2")}</option>
          <option value="g-i">{tr(lang, "band3")}</option>
          <option value="j-l">{tr(lang, "band4")}</option>
        </select>
      )}
      <span className="text-ink/50 font-semibold ms-2">{tr(lang, "lenLabel")}</span>
      <select className={sel} value={value.length} onChange={(e) => set({ length: e.target.value })}>
        <option value="">{tr(lang, "lenAuto")}</option>
        <option value="short">{tr(lang, "lenShort")}</option>
        <option value="medium">{tr(lang, "lenMed")}</option>
        <option value="long">{tr(lang, "lenLong")}</option>
      </select>
    </div>
  );
}
