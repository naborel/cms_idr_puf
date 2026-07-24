# Adding a new quarter

CMS releases a new IDR PUF quarter roughly every 2-3 months, and periodically re-publishes
earlier quarters with corrections. This walks through the process for getting a newly-released
quarter from raw CMS files into `parquet/oon_all_quarters.parquet`, `qpa_all_quarters.parquet`,
and `air_all_quarters.parquet`.

This is the incremental path — it merges one quarter onto the existing parquet files without
re-processing all the others. For a from-scratch rebuild of the entire history, see
`build_parquets.py` instead (requires all raw files for every quarter, which aren't kept in
this repo — see "Data source" in [README.md](README.md)).

## Overview

Three stages, each a separate function call so you see and can act on the output before
anything gets written:

1. **Check** (`puf_checker.check_file`) — validates a raw file against the current parquet's
   schema and known values. Read-only, never writes anything.
2. **Transform** (`puf_transform.transform_quarter`) — normalizes the raw file into the same
   shape as the existing parquet. Reuses the actual normalization functions from
   `build_parquets.py` (`normalize`, `convert_currency_cols`, `force_string_cols`,
   `convert_numeric_cols`, `cast_object_numerics`) so the incremental path and a full historical
   rebuild can never silently drift apart.
3. **Merge** (`puf_merge.merge_quarter`) — concats the transformed quarter onto the existing
   parquet and writes it back out. Defaults to a dry run (reports what would happen, writes
   nothing); pass `dry_run=False` to actually write.

`new_quarter_pipeline.ipynb` (not committed — notebooks are gitignored, it's a local working
file) walks through all three stages as runnable cells and is the easiest way to actually do
this. It's also the fastest way to get moving on the next quarter: open it, update the file
paths at the top, and re-run.

## Step 1: Drop in the raw files

Download the quarter's files from CMS and drop them in the repo root, in whatever folder
structure CMS ships them in — no renaming needed. As of 2025 Q3/Q4, that's a folder per
quarter (e.g. `federal-idr-puf-2025-q3/`) containing individual CSVs for OON, QPA, and Air
Ambulance, plus a combined multi-sheet xlsx and an `Archive/` copy of an earlier pull. Use the
dated CSV files (e.g. `"... (As of January 26, 2026) (CSV).csv"`), not the `Archive/` copies —
CMS revises quarters after initial release, and the dated root-level files are the corrected
version.

The combined xlsx isn't used by this pipeline. For large quarters CMS splits it into multiple
sheets per file type (e.g. `"OON Emergency & Non-Emergency 1"` / `"...2"`) once row counts
exceed Excel's ~1M-row-per-sheet limit, with sheet names that don't match what `build_parquets.py`
expects — the flat CSVs avoid all of that.

None of these raw files get committed — `.gitignore` excludes `*.csv`, `*.xlsx`, and the
`2023/`/`2024/`/`2025/` folders.

## Step 2: Check

```python
from puf_checker import check_file

report = check_file(
    "federal-idr-puf-2025-q3/Federal IDR PUF for 2025 Q3 - OON Emergency & Non-Emergency (As of January 26, 2026) (CSV).csv",
    file_type="oon",       # 'oon' | 'qpa' | 'air'
    quarter="2025Q3",      # see "Quarter format" below
)
report.summary()
```

Run this for all three file types before doing anything else. It streams the raw file in
chunks (doesn't load the whole thing into memory) and reports:

- **Column diff** — columns in the current parquet that are missing from this file, and new
  columns not seen before (these get NaN-backfilled for earlier quarters, which is normal)
- **Unrecognized suppression tokens** — non-numeric values in currency/numeric columns that
  aren't in the known set (`NR`, `N/R`, `^`, `+`, `*`). If you see a new one, sample a few raw
  rows to confirm what it means before assuming it's safe to treat as null (see "Suppression
  markers" below)
- **New categorical values** — values in tracked categorical columns (`Payment Determination
  Outcome`, `Default Decision`, `Initiating Party`, `Health Plan Type`, `Offer Selected from
  Provider or Issuer`, etc.) not seen in any prior quarter
- **Unmapped provider/carrier domains** — ranked by row count, for updating `idr_mappings.py`
  (informational, not blocking — unmapped domains safely fall back to `Unknown`/the raw domain)
- **Quarter collision** — refuses if that quarter is already in the parquet
- **Row-count sanity** — compared to the most recently-added quarter

`report.ok` is `True` if there's nothing that should block a merge (new/unmapped domains are
informational and don't count against it). Read the full report either way — a passing `ok`
doesn't mean nothing changed, just that nothing looks broken.

## Step 3: Transform

```python
from puf_transform import transform_quarter

new_oon = transform_quarter(raw_path, file_type="oon", quarter="2025Q3")
```

`raw_path` can be a single CSV path or a list of paths if CMS ever splits a file into chunks
again (like 2025 Q1/Q2's OON chunk1/chunk2/chunk3 files) — same pattern, just pass a list.

This returns a DataFrame in the exact shape of the existing parquet: suppression tokens
nulled, currency columns converted, `Quarter` tagged, and (for `oon`/`air`) `Provider_Group`,
`Provider_Category`, `Carrier_Group`, `Anthem_Flag`, and `Outcome_Bucket` computed via
`idr_mappings.py`.

## Step 4: Merge

```python
from puf_merge import merge_quarter

merge_quarter(new_oon, file_type="oon", quarter="2025Q3")                # dry run (default) -- reports only
merge_quarter(new_oon, file_type="oon", quarter="2025Q3", dry_run=False) # actually writes
```

Reports the column diff and row-count arithmetic (existing + new = combined), then on
`dry_run=False` loads the existing parquet, concats, and writes atomically (temp file +
`os.replace`) so an interrupted write can never corrupt the existing parquet. Refuses if the
quarter is already present. Doesn't touch git.

Repeat steps 3-4 for `qpa` and `air`. If adding more than one quarter, process them in
chronological order — each merge changes what the next one reads as "existing."

## Step 5: Review and commit

Nothing so far touched git. Once all file types/quarters are merged:

```bash
git status --short   # expect: modified build_parquets.py (if you changed it), modified parquet/*.parquet
git add parquet/oon_all_quarters.parquet parquet/qpa_all_quarters.parquet parquet/air_all_quarters.parquet
git commit -m "..."
git push
```

Do a sanity pass on the merged data before committing — e.g. spot-check `Outcome_Bucket` and
`Provider_Category` distributions for the new quarter(s) aren't degenerate (all one value, all
`Unknown`, etc.):

```python
import pyarrow.parquet as pq
t = pq.read_table("parquet/oon_all_quarters.parquet", columns=["Quarter", "Outcome_Bucket"]).to_pandas()
print(t[t["Quarter"] == "2025Q3"]["Outcome_Bucket"].value_counts())
```

`oon_all_quarters.parquet` and `qpa_all_quarters.parquet` are tracked via git-lfs (see
`.gitattributes`); `git push` uploads the LFS objects alongside the commit, so pushes are
larger/slower than a normal code push.

## Quarter format

Quarter tags in the parquet files are `"2025Q3"` — year first, no space, no leading zero on
the quarter digit. Not `"Q3 2025"`. This matters for every `quarter=` argument above; get it
wrong and `check_file`'s "already present" / row-count-sanity logic won't line up against the
right data.

(`build_parquets.py`'s own `QUARTERS` manifest and CLAUDE.md-style docs from earlier in this
project's history use the `"Q3 2025"` form — that's a historical inconsistency between the
script and what actually ended up in the shipped parquet, not a convention to follow. Match the
data, not the older script.)

## Suppression markers

CMS marks suppressed/missing cells with tokens instead of leaving them blank. Known markers,
tracked in `build_parquets.SUPPRESSION_TOKENS`:

| Token | Since | Where seen |
|---|---|---|
| `NR` / `N/R` | 2023 Q1 | Anywhere |
| `^` | 2025 Q3 | QPA dollar columns (`QPA`, offer amounts) |
| `+`, `*` | 2025 Q3 | "offer as % of QPA" / "as Percent of Median" columns only |

If the checker flags a new unrecognized token, don't assume it's a suppression marker —
sample a few raw rows containing it first (`df[df[col] == token]`) to see what other columns
look like on those rows and confirm it's redaction, not a real (if unusual) value. Once
confirmed, add it to `SUPPRESSION_TOKENS` in `build_parquets.py` — both the full-rebuild path
and the incremental pipeline read from that same list, so it only needs to be added once.

## Known gotchas

- **Windows file-lock on write.** `merge_quarter`'s final `os.replace()` (swapping the temp
  file into place) can fail with `PermissionError: [WinError 5] Access is denied` for anywhere
  from a few seconds to several minutes after writing a large parquet file, cause unconfirmed
  (possibly antivirus real-time scanning, possibly something else in the dev environment) —
  it isn't proportional to file size and isn't fixed by retrying in a fresh process, only by
  waiting. `merge_quarter` retries with a patient backoff (up to ~15 minutes) so this should
  self-heal; if it ever exhausts that and raises, the temp file (`<path>.tmp`) already has the
  fully-written, correct data — just retry the rename once more (`os.replace(tmp_path,
  parquet_path)`) rather than redoing the whole merge.
- **`git diff` on `air_all_quarters.parquet` shows a nonsense size.** This file predates the
  repo's git-lfs tracking (it's a plain git blob, not an LFS pointer, despite `.gitattributes`
  now marking `*.parquet` for LFS), and git's LFS diff driver misreports its diff size as a
  result. Cosmetic only — verify actual file integrity with `pq.ParquetFile(path).metadata`
  or a `Quarter`/row-count check instead of trusting `git diff --stat` for this specific file.
- **The 90%-parseable safety net.** `cast_object_numerics()` auto-converts any object column
  that's >90% numeric-parseable after stripping `$`/`,` — this is what picks up new
  numeric-looking columns (like QPA's `Cost-Sharing Amount`/`Initial Payment Amount`/`Year of
  Service`, added 2025 Q3) without needing code changes. But it also means a genuinely
  categorical column that happens to look mostly numeric (short alphanumeric codes, e.g. CPT
  modifiers) could get silently miscast — if CMS ever actually populates `Service Code
  Modifier(s)` (currently 100% suppressed), double check it didn't get coerced to a numeric
  dtype.
