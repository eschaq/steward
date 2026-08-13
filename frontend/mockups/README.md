# Mockups

Two different things live here — worth not confusing them.

## `built/` — screenshots of the real running app

Rendered by `../verify.mjs` driving a real Chromium against the local backend
with real Firestore data. These are what the app actually looks like.

| File                     | What                                        |
| ------------------------ | ------------------------------------------- |
| `signin-phone.png`       | Sign-in, 402×874 (portrait gable crop)      |
| `signin-desktop.png`     | Sign-in, 1280×860 (landscape crop, offset)  |
| `dashboard.png`          | Inventory, all 24 items                     |
| `dashboard-filtered.png` | Inventory, Contested filter                 |

Regenerate: `cd frontend && node verify.mjs` (needs both servers running). The
originals land in `frontend/` as `verify-*.png` and are gitignored; these copies
are the ones worth keeping.

## The rest — design comps, never built

`signin-mockup.html` and `signin-v2.html` are the decision aids from the sign-in
redesign: the light-mode column, then the hero-bleed and logo options. Open them
in a browser. `c2.jpg` is a CC BY placeholder used only in v2 — see `CREDITS.md`.

Nothing here is served or imported by the app.
