# Quotation System — Design Spec

**Date:** 2026-09-03
**Status:** Approved for planning
**Type:** Internal tool, greenfield

---

## Context

Quoting currently happens in Excel. As the catalog and customer base grow, the
spreadsheet process produces the failure modes it always produces: version
confusion, inconsistent pricing between reps, arithmetic errors, no visibility
into which quotes are outstanding, and no data on what actually converts.

This system replaces that process. It owns customers, the product catalog, and
quotes — it *is* the CRM for this company — and hands accepted quotes off to the
existing ERP/accounting system as sales orders.

The intended outcome: a rep produces an accurate, correctly-priced,
correctly-documented quote in minutes instead of an afternoon, and management
can see the pipeline without asking anyone.

## Operating environment

These constraints shaped most decisions below and are easy to forget later:

- **Company based in China, selling worldwide.** Multi-currency and export
  documentation are core requirements, not later additions.
- **Buyers are international.** Customer-facing links and PDFs must load quickly
  from outside China.
- **Great Firewall constraints apply to both runtime and build tooling.** Google
  Fonts, Vercel, and several common CDNs are unreliable or unreachable from
  mainland China.
- **Solo developer, AI-assisted.** Favor one language, one deploy target, and
  batteries-included libraries over architectural separation that costs
  operational overhead.

## Goals

1. Retire the quoting spreadsheets.
2. Make pricing correct and consistent by construction, not by rep discipline.
3. Produce export-grade documents (quote, proforma invoice) without rework.
4. Give management pipeline visibility and win/loss data.
5. Hand accepted quotes to the ERP without re-keying.

## Non-goals

- Not an ERP. Invoicing, tax filing, fapiao issuance, inventory accounting, and
  shipping execution stay in the existing system.
- Not multi-tenant. One company, one deployment.
- Not a marketing or support CRM. Sales pipeline only.
- No e-signature integration in the initial build — a tokenized acceptance link
  recording timestamp, IP, and name is sufficient.

---

## Architecture

### The core: a pure pricing engine

The single most important structural decision. Pricing lives in one module with
no database access, no framework imports, and no I/O:

```ts
resolveQuote(context: PricingContext): PricedQuote
```

`PricingContext` carries everything needed to price: the catalog snapshot, the
customer's agreement, the lines, the currency, the FX rate, and the effective
date. The caller assembles it; the engine only computes.

Why this matters:

- **Testable.** Hundreds of pricing scenarios run as fast unit tests with no
  database fixtures.
- **Reproducible.** Store the context alongside the result and any historical
  quote can be recomputed and explained, line by line.
- **Auditable.** "Why is this line 42.30?" has a traceable answer.

CPQ systems that scatter pricing across controllers, SQL views, and UI code
become unmaintainable within a year. This boundary is the defence against that,
and it must not be crossed for convenience.

### Modules

| Module | Owns | Depends on |
|---|---|---|
| `pricing` | Price resolution, discounts, margin, rounding | Nothing (pure) |
| `catalog` | Products, variants, UoM, price lists, import | `pricing` types |
| `customers` | Customers, contacts, addresses, agreements | — |
| `quotes` | Quote lifecycle, versioning, numbering, approvals | `pricing`, `catalog`, `customers` |
| `documents` | PDF rendering, templates, fonts | `quotes` |
| `erp-sync` | Outbound sales-order push, CSV fallback | `quotes` |
| `audit` | Append-only event log | — |

Each module should be understandable without reading the others' internals.

### Application shape

Next.js monolith. Server Actions for mutations, React Server Components for
reads, a single Postgres database, background jobs in-process via `pg-boss`.
Deployed as Docker Compose (app + Postgres + Caddy) on one VPS.

No microservices. No Kubernetes. An internal tool for one company needs neither,
and both would cost time that belongs in the pricing engine.

---

## Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Framework | Next.js 15 (App Router), TypeScript strict | One language front to back; Server Actions remove API boilerplate |
| Database | PostgreSQL 16 | JSONB for product configuration; real transactions for gapless numbering |
| ORM | Drizzle | SQL-shaped and predictable; no engine binary to deploy |
| UI | shadcn/ui + Tailwind | Source is vendored into the repo — no CDN dependency |
| Tables | TanStack Table | Quote line editors are dense editable grids |
| Forms | React Hook Form + Zod | Zod schemas shared between client validation and Server Actions |
| Money | dinero.js v2, integer minor units | Floats are disqualifying for money |
| PDF | Playwright → Chromium print-to-PDF | Correct CJK, Arabic, and Cyrillic shaping; `@react-pdf/renderer` handles CJK poorly |
| Auth | Auth.js + WeCom or DingTalk OAuth | Team already authenticates there; email/password fallback |
| Jobs | pg-boss | Postgres-backed — no Redis to operate |
| Storage | S3-compatible (Alibaba OSS or Cloudflare R2) | PDFs, attachments, product images |
| Email | Alibaba DirectMail or Resend | Choose on measured deliverability to international buyers |
| Testing | Vitest (engine, unit) + Playwright (E2E flows) | Effort concentrates on engine tests |
| Errors | Self-hosted Sentry or GlitchTip | Avoids a dependency on a blocked SaaS |

### Hosting

**Alibaba Cloud or Tencent Cloud, Singapore or Hong Kong region.**

Mainland regions require ICP filing for any public-facing domain, and the
customer acceptance link is public-facing. Vercel and most US-hosted platforms
are unreliable from mainland China. Singapore/HK is reachable from the office
and fast for international buyers, with no ICP filing required.

### Build-tooling notes

- Configure `npmmirror.com` as the npm registry, or installs will crawl.
- **Self-host all fonts** (Noto Sans, Noto Sans SC). Google Fonts is unreachable
  from mainland China and would silently break PDF rendering.
- Mirror or vendor the Playwright Chromium download.

---

## Data model

Sketch, not final DDL. Every table carries `created_at`, `updated_at`,
`deleted_at` (soft delete) and `created_by`.

```
customer          id, code, name, country, currency_default, segment,
                  payment_terms_default, incoterm_default
contact           id, customer_id, name, email, phone, role, is_primary
address           id, customer_id, type(billing|shipping), lines, city,
                  country, port_of_discharge

product           id, sku, name_en, name_zh, category, uom, hs_code,
                  country_of_origin, lead_time_days, moq,
                  net_weight_g, gross_weight_g, dim_mm, cbm
product_variant   id, product_id, sku_suffix, attributes(jsonb)

price_list        id, name, currency, valid_from, valid_to, segment
price_list_item   id, price_list_id, product_id, unit_price_minor
volume_break      id, price_list_item_id, min_qty, unit_price_minor | discount_pct

agreement         id, customer_id, valid_from, valid_to,
                  standing_discount_pct, payment_terms, incoterm
agreement_price   id, agreement_id, product_id, unit_price_minor

quote             id, number, customer_id, owner_id, current_version_id, status
quote_version     id, quote_id, version_no, currency, fx_rate, fx_rate_date,
                  valid_until, incoterm, incoterm_place, payment_terms,
                  pricing_context(jsonb), pricing_result(jsonb),
                  totals_minor, sent_at, frozen_at
quote_line        id, quote_version_id, sort, group_label, kind(product|text|
                  freight|insurance|service), product_id, description,
                  qty(numeric), uom, unit_price_minor, discount_pct,
                  line_total_minor, unit_cost_minor, is_optional, is_selected

attachment        id, entity_type, entity_id, filename, storage_key, size
approval          id, quote_version_id, rule, status, approver_id, decided_at
acceptance        id, quote_version_id, token, accepted_at, accepted_by_name,
                  ip, user_agent
audit_event       id, actor_id, entity_type, entity_id, action, payload(jsonb),
                  created_at            -- append-only, never updated or deleted
erp_sync          id, quote_id, status, attempts, last_error, external_ref
```

---

## Invariants

Non-negotiable. Violating any of these is a rebuild, not a bug fix.

1. **All money is an integer in minor units** with an explicit currency code.
   No floating point touches a monetary value at any point.
2. **Quantities are decimals.** 0.5 kg and 2.75 hours are valid.
3. **Rounding is defined once**, applied per line, half-up, and unit-tested.
   The rule lives in the pricing module and nowhere else.
4. **A sent quote version is immutable.** Editing forks a new version. Version 1
   renders identically a year later.
5. **Quote numbers are gapless and sequential** (`Q-2026-0001`), allocated from a
   Postgres sequence inside the sending transaction.
6. **Catalog data is snapshotted onto the quote version.** A later price change
   must not move a historical quote.
7. **The FX rate is locked at quote creation** and stored with its source and date.
8. **The audit log is append-only.** No updates, no deletes, ever.
9. **All timestamps are `timestamptz`**, stored UTC, rendered in the viewer's zone.
10. **Deletes are soft.** Nothing is destroyed.

---

## Scope by phase

Each phase is independently useful and shippable. **This spec deliberately
describes more than one implementation plan should cover.** Phases 0 and 1 are
the first planning unit; phases 2–6 get their own plans once earlier phases are
in real use and the requirements have sharpened.

### Phase 0 — Foundation

Auth (WeCom/DingTalk + fallback), roles, base schema, money primitives, audit
log, and catalog import from Excel with column mapping, dry-run preview, and
per-row error reporting. Re-import matches on SKU and updates rather than
duplicating.

### Phase 1 — Quoting that retires the spreadsheets

The value-delivering milestone. Target ~6 weeks.

- Create a quote from scratch, from a template, or by duplicating an existing one
- Keyboard-first line entry: SKU autocomplete, paste from spreadsheet
- Line reorder, grouping, section headers, free-text lines
- Per-line and per-quote discounts (% and fixed)
- Live margin display with a warning threshold
- Validity period with automatic expiry
- PDF generation and email send
- Status: `draft → sent → accepted | rejected | expired`
- Quote list with filters and full-text search
- **CSV export of accepted quotes** — the ERP handoff fallback, usable long
  before the API integration exists

### Phase 2 — The pricing engine proper

Customer agreements and contract prices, segment price lists, volume breaks, and
multi-currency with locked FX rates.

Price resolution precedence:

```
agreement price → volume break → segment price list → list price
  → standing discount → manual discount
```

Every resolution step is explainable in the UI: the rep can see which rule
produced the number.

### Phase 3 — Governance

Versioning with side-by-side comparison, approval workflow (thresholds on
discount %, margin floor, and total value), and the customer acceptance portal —
a tokenized public link recording timestamp, IP, and name.

### Phase 4 — Export documentation

Incoterms 2020 with named place, HS codes and country of origin, package data
(net/gross weight, dimensions, cartons, CBM), port of loading and destination,
lead time and MOQ, structured payment terms (e.g. 30% T/T deposit, 70% against
B/L), freight and insurance as distinct non-discountable line kinds, bilingual
EN/中文 documents, and **proforma invoice generation from an accepted quote** —
the document international buyers actually need.

Tax treatment: exports are handled as zero-rated, domestic sales carry standard
VAT. The system records the treatment on the quote but does not compute filings —
that remains the ERP's responsibility. *Confirm the specific export rebate
treatment with the company's accountant before implementing.*

### Phase 5 — Product configurator

Formula-priced and option-configured products. Deliberately last: this is where
CPQ projects fail. By this point the real requirement will be known, and it may
turn out that a formula field plus a few option lists covers the handful of
products that need it — in which case a general-purpose configurator should not
be built at all.

### Phase 6 — Close the loop

ERP sync (accepted quote → sales order, idempotent, with per-quote sync status
and manual retry), dashboards, and win/loss analytics.

---

## Documents

- Templates are HTML + token substitution, editable without a redeploy.
- Rendering is deterministic: the same quote version produces the same PDF
  indefinitely.
- Company letterhead, company chop/stamp image, and signature block.
- Terms & conditions appended as a final page.
- **Fonts are self-hosted and embedded** (Noto Sans, Noto Sans SC).

## Non-functional requirements

- Role-based access: rep sees own quotes, manager sees the team, admin sees all.
- Automated Postgres backups **with a restore procedure that has actually been
  executed and verified** — an untested backup is not a backup.
- Error tracking and structured logging.
- Full-text search across quotes, customers, and products.
- Mobile-readable read views. Reps check status from phones; they do not build
  quotes there. Quote editing is desktop-only by design.

## Testing strategy

Effort is deliberately unbalanced toward the engine.

- **Pricing engine:** exhaustive unit tests. Every precedence path, every
  rounding edge, every discount combination, negative and zero cases,
  multi-currency. This is the test suite that matters.
- **Invariants:** dedicated tests for immutability of sent versions, gapless
  numbering under concurrency, and audit-log append-only behaviour.
- **Import:** fixture spreadsheets including deliberately malformed ones.
- **E2E (Playwright):** the happy path — create quote, price it, send it, accept
  it — plus PDF rendering with CJK content.

## Open questions

Resolve before or during Phase 0:

1. Which ERP/accounting system, and does it expose a usable API?
2. WeCom or DingTalk for SSO?
3. Which currencies at launch, and what is the FX rate source?
4. Approval thresholds — what discount or margin floor triggers review, and who
   approves?
5. Roughly how many products and customers migrate from the spreadsheets?

## Decision log

| Decision | Alternatives considered | Why |
|---|---|---|
| Next.js monolith | Supabase + React; Refine/Directus admin framework | Supabase splits pricing logic across edge functions and RLS; admin frameworks scaffold the CRUD but fight you on the quote builder, which is ~70% of the value |
| Pure pricing engine module | Pricing in services / DB views | Testability, reproducibility, explainability |
| Playwright PDF | `@react-pdf/renderer` | CJK rendering correctness |
| Drizzle | Prisma | No engine binary; simpler deployment on restricted networks |
| pg-boss | BullMQ + Redis | One fewer service to operate |
| Singapore/HK hosting | Mainland China; Vercel | No ICP filing needed; reachable both from the office and by international buyers |
| Configurator last | Configurator early | Highest-risk component; requirements clarify with use |
