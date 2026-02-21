# PrUnderground Changelog

## 1.1.2 — Seller Identity & Sort Improvements (2026-02-08)

### Features

- **Seller identity** — new `User.md_name` and `User.discord_username` columns. Seller column on browse page shows MD name when set, falls back to FIO username. Discord username shown on public profile only.
- **Default sort improvements** — browse page default sort now shows available items first (in stock/low stock above out of stock), most recently updated as tiebreaker within availability groups. Stock status column is now sortable.
- **Copy-to-clipboard buttons** — copy buttons on listing fields (material, price, location, seller name) for easier contract creation in APEX.

### Security

- **Auth bypass fix** — fixed `/auth/check-user` endpoint that allowed session creation without credential proof.
- **CSRF on all POST endpoints** — added `verify_csrf` to import and admin endpoints.

### Migration

```bash
python scripts/add_contact_columns.py
```

---

## 1.1.1 — Theme Persistence & Embed Protocol (2026-02-07)

### Features

- **Theme persistence** — theme preferences (color palette, tile style) now saved to database. Previously only stored client-side.
- **Embed protocol** — postMessage protocol for embed mode (`?embed=1`): `pru:ready` on load, `pru:navigate` on link clicks. Enables rPrUn host to react to PrUnderground navigation.

### Fixes

- Discord `{date}` variable now uses current time instead of last FIO sync timestamp.

### Migration

```bash
python scripts/add_theme_columns.py
```

---

## 1.1.0 — Theme Customization & Bundle Status (2026-02-05)

### Features

- **Theme customization** — 4 color palettes (Refined PrUn, PrUn Default, High Contrast, Monochrome), 2 tile styles (Filled, Lite). Live preview in Account Settings.
- **Bundle status column** — STATUS column on dashboard, browse, and profile bundle tables. Responsive badges: IN STOCK (green), LOW (orange), OUT (red), MTO (purple), ∞ (cyan). Three-tier responsive rendering (badge → dot → colored qty).
- **Browse page improvements** — collapsible filter section, active filters as removable pills, unified filter UI between listings and bundles.

### Fixes

- Fixed 450-540px breakpoint gap for qty/status handoff.
- Fixed wide-medium tier (724-986px) table overflow.
- Fixed button spacing in action columns.

---

## 1.0.5 — Low Stock, Discord Templates, CX Prices, Admin (2026-01-29)

### Features

- **Low stock threshold** — user-defined threshold per listing (default: 10) and bundle (optional).
- **Discord templates** — user-customizable Discord copy format with variables (`{company_code}`, `{username}`, `{date}`, `{material}`, `{quantity}`, `{price}`, `{location}`, `{profile_url}`).
- **CX price display** — background sync every 30 minutes via APScheduler. Shows calculated prices for CX-relative listings (e.g., "CX.NC1-5%").
- **Admin dashboard** — usage telemetry + admin stats at `/admin/stats` (requires `ADMIN_USERNAMES` env var).

### Fixes

- Fixed stock quantity text colors on browse/profile pages.

### Dependencies

- Added `apscheduler>=3.10.0`

### Migration

```bash
python scripts/add_low_stock_threshold.py
python scripts/add_discord_template.py
python scripts/add_exchange_table.py
python scripts/add_usage_stats.py
```

---

## 1.0.4 — Bundle Stock Modes (2026-01-27)

### Features

- **Bundle stock modes** — MANUAL (existing), UNLIMITED (∞ symbol), MADE_TO_ORDER (badge + optional ready qty), FIO_SYNC (computed from FIO storage with live inventory preview).
- Form buttons restructured: Submit/Cancel side-by-side, Delete on separate row.
- Added missing Delete button to listing edit form.

### Migration

```bash
python scripts/migrate_bundle_stock_mode.py
```

---

## 1.0.3 — Security & Mobile UI (2026-01-25)

### Security

- FIO API keys encrypted at rest (Fernet).
- Removed legacy unsigned cookie bypass.
- Fixed innerHTML XSS vulnerability.
- Tightened CSP frame-ancestors.

### Features

- **Four-tier responsive CSS** (≤540px, 541-723px, 724-986px, >986px).
- **Cross-origin authentication** for APEX iframe embedding.
- Hamburger menu for narrow viewports.
- Debug URL params: `?embed=1`, `?narrow=1`, `?chrome=0`.

### Hotfixes

- X-Forwarded-Proto detection for Cloudflare Tunnel HTTPS detection.
- Container max-width enforcement at desktop breakpoint.
- ProxyHeadersMiddleware for X-Forwarded-Proto behind Cloudflare.
- Automatic cache-busting via file mtime query strings.
