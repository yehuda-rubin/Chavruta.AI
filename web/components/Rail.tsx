import { Icon } from "./Icon";

// A collapsed panel — a thin vertical rail with an expand button, matching the static UI's rails.
export function Rail({
  side,
  icon,
  title,
  onExpand,
  extra,
}: {
  side: "start" | "end"; // which chevron points "open"
  icon: string;
  title: string;
  onExpand: () => void;
  extra?: React.ReactNode;
}) {
  const chevron = side === "start" ? "chevron_left" : "chevron_right";
  return (
    <div className="w-14 shrink-0 glass rounded-[28px] p-2 flex flex-col items-center gap-3">
      <button
        onClick={onExpand}
        className="h-10 w-10 rounded-2xl glass grid place-items-center text-tekhelet hover:bg-white/60 transition"
        title={title}
      >
        <Icon name={chevron} />
      </button>
      {extra}
      <Icon name={icon} className="text-ink/35 mt-1" />
    </div>
  );
}
