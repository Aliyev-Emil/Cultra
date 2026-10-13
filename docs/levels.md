# Levels (XP)

Built: see `current_level()`, `award_xp()`, `xp_for_merchant_payment()` and `GET /rewards/{user_id}`
in `main.py`, the level card on the Keşbek page (`cashback.html`) and the badge on the home page.

Customers earn XP by using Cultra at merchants. XP builds a **level**, and a higher level
**raises the monthly cashback caps**. Levels are based on recent use only, so they go
down again when someone stops using the app.

No streaks, no monthly challenges, no random rewards.

## Earning XP

| Action | XP | Limits |
|---|---|---|
| Paying a merchant (scanning their QR, or approving their checkout request) | +10 | Payment must be ₼1 or more. Only the first 5 payments a day earn XP. |
| First payment ever at a merchant | +25 | Once per merchant. |
| Someone you sent money to (by username) makes their first merchant payment | +100 | Once per person. |

No XP for top-ups, receiving money, or sending money between users: those don't show
real use and are easy to farm (two friends sending the same ₼10 back and forth).

## The time range: 90 days

Every XP entry counts for 90 days, then expires. A user's XP is always
"what they earned in the last 90 days".

- 30 days would be too jumpy (one holiday and the level is gone).
- A year would be too slow (people keep a high level long after they stopped).

## Levels

| Level | Reach at | Keep if ≥ (on the 1st) | Cashback caps |
|---|---|---|---|
| Bronze | 0 XP | — | base caps |
| Silver | 300 XP | 210 XP | base caps × 1.25 |
| Gold | 1,000 XP | 700 XP | base caps × 1.5 |
| Platinum | 2,500 XP | 1,750 XP | base caps × 2 |

Roughly, at 10 XP per payment: Silver ≈ 2–3 payments a week, Gold ≈ one a day,
Platinum ≈ 2–3 a day. New-merchant and referral XP get people there faster.

## Going up and going down

- **Going up is instant.** As soon as the 90-day XP reaches a level's "reach" number, the
  user ranks up and gets the bigger caps straight away.
- **Going down is only checked on the 1st of each month**, the same day the cashback caps
  reset. If the 90-day XP is below the current level's "keep" number, the user drops
  **one** level.

Why:

- Dropping on the 1st means nobody loses cashback limit in the middle of a month.
- "Keep" is 70% of "reach", so someone sitting right at 1,000 XP doesn't flip between
  Gold and Silver every time they skip a few days.
- One level per month makes the decline gradual instead of a punishment.

**Example.** Emil pays almost daily and reaches Gold on 20 October, then stops.

| Date | 90-day XP | Result |
|---|---|---|
| 1 November | ~910 (≥ 700) | stays Gold |
| 1 December | ~560 (< 700) | drops to Silver |
| 1 January | ~200 (< 210) | drops to Bronze |

He climbs back up the moment he starts paying again.

## What the user sees

- **Main menu:** the level next to the greeting, e.g. "Salam, Emil · 🥇 Gold".
- **Keşbek page (top):** level, XP in the last 90 days, a bar to the next level, and the
  line that matters most: "To keep Gold on 1 December you need 700 XP. You have 860 ✓"
  (or how many are missing).
- **Payment banner:** "₼18.40 ödənildi · +₼0.33 keşbek · +10 XP".

## Backend notes

- Each user gets a `rewards` record (created the first time it's needed): `xp_events`
  (date, XP, reason), `level`, `checked` (the month of the last "1st of the month" check),
  `paid_merchants` and `referred_by`.
- `xp_for_merchant_payment()` is called from `/pay` and `/confirm-payment` (merchant payments
  only). It applies the ₼1 minimum, the 5-a-day limit, the new-merchant bonus and the referral.
- `award_xp()` adds an entry and ranks the user up straight away when they reach the next level.
- `current_level()` is the monthly check. It needs no timer: the first time a user is looked at
  in a new month, it replays every 1st since the last check (at most one drop each).
- `apply_cashback()` uses `monthly_cap × level multiplier`.
- `/send` remembers who first sent money to someone who has never paid a merchant (the referral).
- `GET /rewards/{user_id}`: level, 90-day XP, next level, the "keep" check for the next 1st
  (date, XP needed, XP the user will have by then), all levels and the XP rules. Feeds the
  Keşbek page and the main-menu badge.
