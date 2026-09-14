# Publishing a rebuild

The repo carries **structure and data**: the parquets, the scripts that build them, and the
carrier/provider crosswalks. Analysis output (dashboard, methodology, notebooks) is ignored.

## One-time check

Git LFS is already configured for `*.parquet` — nothing to set up. Confirm it is installed:

```bash
git lfs version          # if this fails: https://git-lfs.com
```

## Publish

```bash
cd ~/PycharmProjects/cms_idr_puf

python publish_parquets.py --check     # verify row counts, write nothing
python publish_parquets.py             # recompress to ZSTD, write into parquet/

git add -A
git commit -m "Rebuild parquets from raw CMS files; add carrier/provider crosswalks"
git push
```

`publish_parquets.py` refuses to write if the rebuilt files have fewer rows or fewer columns
than what is already published, so a bad rebuild cannot silently overwrite a good one.

## Watch the LFS quota

GitHub's free allowance is **1,024 MB of LFS storage and 1,024 MB/month of bandwidth**, and
**LFS keeps every version you ever push** — old blobs are not freed by overwriting the file.

| | Size |
|---|---|
| Already in LFS (previous parquets) | ~412 MB |
| This push, recompressed to ZSTD | ~337 MB |
| **LFS store after the push** | **~749 MB of 1,024 MB** |

That leaves room for roughly one more rebuild before the free tier is exhausted. Each fresh
`git clone` also pulls ~337 MB against the monthly bandwidth allowance, so three clones in a
month will hit the ceiling.

Options when it gets tight:

- **Buy a data pack** — $5/month per 50 GB storage + 50 GB bandwidth. Simplest fix.
- **Move the data to a Release.** Release assets allow up to 2 GB per file, do not count against
  LFS, and are not version-retained. Good if only the newest quarter set matters.
- **Rewrite LFS history** with `git lfs prune --verify-remote` plus a server-side purge, to drop
  superseded blobs. Effective but destructive; take a backup first.

## What is deliberately not in the repo

`dashboard/`, `METHODOLOGY.md`, notebooks, and `*.html` are gitignored. They are findings built
on top of this data, and they change far more often than the data does.
