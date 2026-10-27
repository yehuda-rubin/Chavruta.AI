"use client";
import { useCallback, useEffect, useState } from "react";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { api } from "@/lib/api";

// The student's side of linking (spec 009): approve or decline a school join request and a parent's
// link request. Nothing is linked until the student says yes. Renders nothing when there is nothing
// pending, so an account that never receives a request sees no change in Settings.
export function LinkRequests({ lang }: { lang: Lang }) {
  const [schools, setSchools] = useState<{ id: number; org_name: string }[]>([]);
  const [parents, setParents] = useState<{ parent_owner_id: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [j, p] = await Promise.allSettled([api.joinRequests(), api.parentLinks()]);
    setSchools(j.status === "fulfilled" ? j.value.requests : []);
    setParents(p.status === "fulfilled" ? p.value.links.filter((l) => l.status === "pending") : []);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch {
      setError(tr(lang, "linkReqFailed"));
    } finally {
      setBusy(false);
    }
  };

  if (!schools.length && !parents.length && !error) return null;

  const Buttons = ({ onYes, onNo }: { onYes: () => void; onNo: () => void }) => (
    <div className="flex gap-2">
      <button disabled={busy} onClick={onYes}
              className="px-3 py-1.5 rounded-xl grad text-white text-xs font-semibold disabled:opacity-50">
        {tr(lang, "linkReqApprove")}
      </button>
      <button disabled={busy} onClick={onNo}
              className="px-3 py-1.5 rounded-xl glass text-ink/70 text-xs font-semibold disabled:opacity-50">
        {tr(lang, "linkReqDecline")}
      </button>
    </div>
  );

  return (
    <div className="mt-2 p-3 rounded-2xl glass border border-tekhelet/20 flex flex-col gap-3" role="region"
         aria-label={tr(lang, "linkReqHeading")}>
      <h4 className="font-semibold text-xs text-tekhelet">{tr(lang, "linkReqHeading")}</h4>
      {schools.map((r) => (
        <div key={`s${r.id}`} className="flex flex-col gap-2">
          <p className="text-xs text-ink/80 leading-relaxed">{tr(lang, "linkReqSchool").replace("{name}", r.org_name)}</p>
          <Buttons onYes={() => run(() => api.decideJoinRequest(r.id, "approve"))}
                   onNo={() => run(() => api.decideJoinRequest(r.id, "decline"))} />
        </div>
      ))}
      {parents.map((l) => (
        <div key={`p${l.parent_owner_id}`} className="flex flex-col gap-2">
          <p className="text-xs text-ink/80 leading-relaxed">
            {tr(lang, "linkReqParent").replace("{id}", l.parent_owner_id)}
          </p>
          <Buttons onYes={() => run(() => api.decideParentLink(l.parent_owner_id, "approve"))}
                   onNo={() => run(() => api.decideParentLink(l.parent_owner_id, "decline"))} />
        </div>
      ))}
      {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
