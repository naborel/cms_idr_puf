# Mapped dollar fields on `oon_all_quarters.parquet`

Fourteen columns appended to every OON dispute line. They carry the real dollar
amounts CMS publishes on the **QPA & Offers** sheet but never keys back to the
dispute, recovered by the match ladder (`claude/idr-match-ladder.md`).

## The columns

| Column | Type | Meaning |
|---|---|---|
| `Dollars Matched` | bool | true on the 5,740,555 lines that carry a QPA dollar |
| `Match Rung` | int | 1–4, the rung that resolved it (1 = tightest key) |
| `Match Rung Name` | str | e.g. `Rung 2 - no party/IDRE` |
| `Ratios Used` | str | which published percentages formed the key: `P`rovider, plan (`H`), `M`edian — e.g. `PHM`, `P--` |
| `Candidates in Tie` | int | how many QPA-sheet rows the key returned. 1 = a single row; >1 = a block that agreed |
| `Match Type` | str | `Single QPA line` or `Tied block` |
| `QPA ($)` | double | **the recovered QPA** |
| `Median QPA ($)` | double | peer-group median (quarter × code × region) |
| `Provider/Facility Offer ($)` | double | provider's offer in dollars |
| `Health Plan/Issuer Offer ($)` | double | carrier's offer in dollars |
| `Prevailing Offer ($)` | double | the winning side's offer |
| `Median Tied` | bool | candidates agreed on the median |
| `Provider Offer Tied` | bool | candidates agreed on the provider offer |
| `Plan Offer Tied` | bool | candidates agreed on the plan offer |

A dollar column is null where the candidates did not agree on that particular
value, even when they agreed on the QPA. The `* Tied` flags say which.

## The one rule behind all of it

> **A match is: every candidate row on the QPA sheet carries the same QPA
> dollar, within ±$0.01.**

That test never changes. Only the key loosens, across four rungs. Nothing is
derived by multiplying a rounded percentage; nothing carries a tolerance.

## Coverage

| | Lines | |
|---|---|---|
| All OON dispute lines | 8,233,903 | |
| Publish at least one percentage (keyable) | 6,791,943 | 82.5% |
| **Dollars attached** | **5,740,555** | **69.7% of all · 84.5% of keyable** |
| of which defaulted disputes | 988,398 | |
| Publish no percentage at all — unkeyable | 1,441,960 | 17.5% |

## Validation

The published percentage is part of the key, so a matched row reproduces it by
construction — that check is worthless. Validation is by holdout: hide a ratio,
re-run the whole ladder, see whether it lands on the same dollar.

| Holdout | Still answered | Same dollar to the cent |
|---|---|---|
| Hide the median ratio | 90.9% | **99.91%** |
| Hide median + plan (what a defaulted line carries) | 65.8% | **99.70%** |

Accuracy barely moves as the key weakens; coverage falls instead. The ladder
refuses rather than guesses.

## Joining to anything else

The portable key is **`Dispute Number` + `DLI Number` + `Quarter`** — unique
across all 8,233,903 rows. `(Dispute Number, DLI Number)` alone is NOT: 8,430
pairs appear twice (16,863 rows), because a dispute line republished in a later
quarter keeps its identifiers.

```sql
-- carrier behaviour against the QPA, contested lines only
select "Carrier_Group",
       count(*)                                   as lines,
       median("QPA ($)")                          as median_qpa,
       median("Health Plan/Issuer Offer ($)")     as median_plan_offer,
       median("Provider/Facility Offer ($)")      as median_provider_offer,
       median("Health Plan/Issuer Offer ($)" / "QPA ($)") as plan_offer_x_qpa
from read_parquet('data/oon_all_quarters.parquet')
where "Dollars Matched"
  and "Default Decision" = 'No'
  and "Health Plan/Issuer Offer ($)" is not null
group by 1
having count(*) >= 2000
order by lines desc;
```

## What is not claimed

1. A match identifies the **dollars**, not always the dispute — 38.2% resolve to
   one specific QPA-sheet row; the rest give the dollars and the carrier.
2. Price statistics, not outcome statistics. Win and default rates belong on the
   full line count, where nothing is missing.
3. Geography is not in this file. A region is only known where every candidate
   agreed on one; that column is a planned addition.
4. Service code modifiers are unusable (populated on 0.9% of lines).
5. Air ambulance is out of scope — separate sheet, never matched.
