# CLAUDE.md

QuoteDesk: a local, single-user price catalog + quotation app for one seller at Shenzhen Sixunited.

- **Spec:** `docs/QUOTEDESK_PLAN.md` (authoritative; built milestone by milestone, M0→M6).
  `docs/superpowers/specs/2026-09-03-quotation-system-design.md` is the superseded Next.js design: history only.
- **Document formats:** `docs/examples/` holds the PDFs QuoteDesk must reproduce (offer, quotation list,
  proforma invoice); plan §5.3–5.4 describes them.
- **Decisions:** `DECISIONS.md`. When the plan leaves room, pick the simplest option and record it there.
  Ask the owner only when the plan contradicts itself.
- **Progress:** the Status line in `README.md` says which milestones are done.

## Stack

FastAPI + SQLAlchemy 2 + Alembic + SQLite (WAL, FTS5 trigram) in `backend/`; React 18 + TS + Vite +
Ant Design 5 + TanStack Query + react-i18next in `frontend/`. FastAPI serves `frontend/dist` at `/`.

## Commands

```bash
cd backend && ../.venv/bin/pytest -q            # tests (fixtures in backend/tests/fixtures)
cd backend && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check . && ../.venv/bin/mypy
cd backend && ../.venv/bin/python -m app --reload   # API on 127.0.0.1:8765 (migrates + seeds on start)
cd frontend && npm run dev                      # UI on :5173, proxies /api
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Rules that matter

- **Never bind anything but 127.0.0.1.** There is no auth by design.
- **Money is Decimal end to end.** DB columns use the `Money` type (TEXT); the API returns strings; the
  frontend formats with `lib/money.ts` (BigInt), never `Number` for displayed amounts.
- **All product writes go through `services/catalog.py`** so the fingerprint, denormalized current price
  and FTS index stay in sync. Normalization and fingerprint live in `services/importer/normalize.py` and
  stay pure (no DB).
- **Last upload wins:** the newest `price_history` row is current per (product, tier), whatever its `price_date`.
- **Every UI string goes through `t()`** with keys in both `frontend/src/i18n/en.json` and `zh.json`;
  `npm run lint` fails otherwise. API errors are RFC 7807 with an i18n `key` (frontend: `errors.<key>`).
- `ProblemError(status, key, detail, **params)`: the first three are positional-only.
- New migration: autogenerate, then replace `app.models.base.Money(...)` with `sa.String(length=32)`.
- Ant Design inserts a space into two-character CJK button labels (`编 辑`): match on that in browser tests.
- Quotes: only drafts change (`quote.locked`); lines are snapshots. Pricing lives in
  `services/quotes.py`; documents in `services/documents/` (fpdf2 + openpyxl). Previews of the three
  sample layouts are the fastest check after touching a renderer. Combined products are `config` lines
  whose cost is recomputed from `components`; saved builds live in `services/configurations.py`
  (catalog parts always price live). Customer documents never print cost; the internal
  version (`?internal=true`, `documents/internal.py`) does.
- Three AI providers (Settings → `llm_provider`): `ClaudeExtractor`, `GeminiExtractor` and
  `GroqExtractor` in `services/importer/llm_parser.py` share prompt and schema; keys live in
  `data/.env` only.
- Import tests replay recorded model output (`tests/importer_fakes.py`) and patch `pipeline.spawn` /
  `pipeline.make_extractor`; live model checks are `pytest -m live` with `QUOTEDESK_LIVE=1`.
- Imports without AI: `services/importer/mapping.py` turns mapped columns into the AI's row shape;
  keep both paths producing the same dict.
- Desktop build: `backend/packaging/quotedesk.spec`; paths go through `config.BUNDLE_DIR` (read-only
  bundle) and `config.APP_DIR` (data next to the exe). New runtime files must be added to the spec.
- Autogenerate ignores `products_fts*` (see `alembic/env.py`); hand-check new migrations anyway.
  Prefer plain `ADD COLUMN` over batch table rebuilds; migrations run with SQLite foreign keys off.
