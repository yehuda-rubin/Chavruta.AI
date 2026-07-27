# Session records — history, not instructions

Dated accounts of individual working sessions. They were at the repository root, where a reader
reasonably takes a file for current guidance; they are not. **Nothing here is maintained, and none of
it should be followed as a procedure.**

They are kept rather than deleted because each one records *why* something was done, which the code
and the current docs state but do not explain.

| file | what it records | where the current version lives |
|---|---|---|
| `SESSION_SUMMARY_2026-07-12.md` | the ref-format anchoring bug (router dots vs corpus spaces) and the Talmud perek→daf numbering (`N = 2·daf ∓ 1`) | `docs/CORPUS.md §7.2`, `§7.3` |
| `SESSION_SUMMARY_2026-07-13.md` | the Yerushalmi tier being added, and the move to the Nebius API as the default even locally | `README.md`, `CLAUDE.md`, `docs/CORPUS.md` |
| `NIGHT_WORK_SUMMARY.md` | an autonomous overnight session (2026-07-09) | superseded throughout |
| `RESUME_LOCAL_LOAD.md` | resuming a paused load of the old mixed-licence `chavruta` collection | **superseded** — that collection was deleted 2026-07-20; see `docs/COMMERCIAL_CORPUS.md` |

Two things in here are actively wrong if read as current:

- `NIGHT_WORK_SUMMARY.md` describes changing Windows sleep settings with `powercfg` and says a commit
  was pushed to `origin`. Neither is a standing instruction, and the branch has not been pushed since.
- `RESUME_LOCAL_LOAD.md` resumes a load of a collection that **no longer exists**. Its own banner says
  so; the procedure below that banner must not be run.
