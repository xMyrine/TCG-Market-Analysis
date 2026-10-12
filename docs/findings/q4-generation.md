# Q4 — Which generation of Pokémon cards is most expensive?

*First pass, price snapshot of 2026-10-11. Reproduce with `python -m analysis.q4_generation`.*

## Data

- 40,837 price series (one per card × printing) of Pokémon single cards with a market price,
  from 193 sets. Code Cards, sealed product and presales excluded.
- **Era** = Pokémon TCG series, assigned from each set's release date (start of the first set
  of each series: Base Set 1999-01-09, EX 2003-06, DP 2007-05-23, HGSS 2010-02-10, BW 2011-04-25,
  XY 2014-02-05, SM 2017-02-03, SWSH 2020-02-07, SV 2023-03-31, ME 2025-09-26).

## Step 1 — medians of price per era

Prices are close to log-normal (the mean is pulled up by a few chase cards), so the typical
card is described by the median and the geometric mean `exp(mean(log p))`.

| Era | Series | Sets | Median $ | Geometric mean $ | p90 $ | Share ≥ $10 |
|---|---|---|---|---|---|---|
| WotC | 3,351 | 19 | 14.81 | 14.55 | 160.99 | 56% |
| EX | 3,377 | 18 | 16.23 | 11.80 | 124.33 | 58% |
| DP/Pt | 2,705 | 15 | 3.88 | 4.15 | 41.49 | 30% |
| HGSS | 1,030 | 6 | 5.54 | 5.46 | 52.87 | 37% |
| BW | 2,953 | 19 | 1.87 | 2.59 | 34.38 | 22% |
| XY | 4,898 | 26 | 1.08 | 1.85 | 29.62 | 21% |
| SM | 6,938 | 24 | 0.78 | 1.23 | 13.94 | 13% |
| SWSH | 6,757 | 30 | 0.30 | 0.52 | 6.21 | 7% |
| SV | 6,747 | 26 | 0.25 | 0.51 | 10.34 | 10% |
| ME | 2,081 | 10 | 0.26 | 0.49 | 6.55 | 8% |

Raw medians mix *age* with *what each era contains* (printings, rarity ladders), so they are
only descriptive.

## Step 2 — hedonic regression

`log(price) ~ era + rarity + printing (normal/reverse/holo) + 1st edition + card class`

- **Reference:** Scarlet & Violet, Common, normal printing, Pokémon card. An era coefficient `b`
  gives the price ratio `exp(b)` for an otherwise identical card (a ratio of geometric means).
- **Identification:** rarities that exist in a single era (e.g. Special Illustration Rare) are
  absorbed by their own dummy and say nothing about era. Era effects come from the rarities
  shared across eras, so a like-for-like spec on Common/Uncommon/Rare/Holo Rare is reported too.
- **Standard errors clustered by set.** Era is constant within a set, and cards in a set share
  demand shocks, so the effective sample size is the ~190 sets, not 40k cards (the Moulton
  problem). Clustered SEs came out 4–9× larger than naive OLS SEs; naive SEs would have
  declared SWSH "significantly cheaper than SV" (t = −8) where the clustered t is −0.9.

**Like-for-like (n = 32,463 series, 161 sets, R² = 0.70):**

| Era | Price ratio vs SV | 95% CI |
|---|---|---|
| WotC | 57× | 34–97× |
| EX | 36× | 29–45× |
| DP/Pt | 13× | 11–15× |
| HGSS | 17× | 13–22× |
| BW | 5.7× | 4.6–7.0× |
| XY | 3.3× | 2.6–4.2× |
| SM | 3.5× | 1.9–6.4× |
| SWSH | 1.0× | 0.7–1.3× |
| ME | 0.8× | 0.7–1.0× |
| 1st Edition (flag) | 1.5× | 0.9–2.7× |

All rarities with rarity fixed effects (n = 40,837, 193 sets) gives nearly identical era
ratios (WotC 60×, EX 37×, … SWSH 1.0×), so the result does not hinge on the exotic rarities.

## Interpretation

- Older eras are far more expensive, but not monotonically: HGSS above DP/Pt, and no premium
  at all for SWSH (2020–23) over SV. Consistent with print-run size (small runs in EX/HGSS,
  record printing in the 2020–21 boom).
- The raw medians put EX above WotC; with controls WotC is clearly first, so EX's lead was
  composition.
- The 1st Edition premium is not pinned down: only 19 WotC sets carry that variation.
- Era, rarity and printing explain 70% of the variance of log price; the rest is card-specific.

## Caveats

- **Age vs cohort.** In one snapshot, age = snapshot date − release date, so age and era are
  the same variable. This shows that older eras are *priced* higher, not that cards
  *appreciate*. Separating the two needs the same cohorts observed over time.
- **Label drift.** A "Holo Rare" was the top pull in 1999 and is mid-tier today; the model
  assumes a label means the same across eras.
- **Condition and survival** of old physical cards are not controlled.
- **Selection.** Series without a market price (0.4% of singles, mostly expensive cards) are
  excluded.

## Next

Card-level features for the remaining 30%: Pokémon popularity (Charizard, Pikachu, Eeveelutions),
tournament play (Limitless), illustrator. Re-run on later snapshots to check stability.
