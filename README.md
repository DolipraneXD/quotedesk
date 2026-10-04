# QuoteDesk

A local, single-user price catalog and quotation tool for Shenzhen Sixunited Technology.
It imports supplier price lists (Excel, screenshots, PDF), keeps the price history of every product, and
builds quotations in the company's format.

The full specification is [docs/QUOTEDESK_PLAN.md](docs/QUOTEDESK_PLAN.md); implementation choices are in
[DECISIONS.md](DECISIONS.md).

**Status:** all milestones (M0–M6) are done: catalog, AI and manual imports (Excel, screenshots, PDF),
customers, quotes, combined products and configurations, proforma invoices, PDF/Excel export,
dashboard, backups and the Windows desktop build.

**For the seller:** see the install and user guide, [in English](docs/INSTALL.md) or
[in Chinese (中文)](docs/INSTALL.zh-CN.md).

### Importing a price list

1. Settings → General → AI import: pick the provider (**Anthropic Claude**, **Google Gemini** or
   **Groq**), paste its API key, then **Test connection** (it saves first). Anthropic keys start with
   `sk-ant-` (console.anthropic.com); Gemini keys start with `AIza` (aistudio.google.com/apikey); Groq
   keys start with `gsk_` (console.groq.com/keys; the free tier is too small for real imports, so use
   the Dev Tier).
2. Imports: drop one `.xlsx` / `.csv` file, or any number of screenshots (`.png`, `.jpg`) and PDFs.
   Screenshots dropped together become one import. Every sheet, screenshot and PDF page is listed;
   price-like visible sheets are pre-ticked (tick hidden ones if needed). A category hint per source is
   optional.
3. **Extract**: the AI reads spreadsheets in batches of 60 rows, and each screenshot or PDF page in one
   go (progress is live; you can cancel).
4. **Review**: every row is New / Updated / Unchanged / Possible match / Problem. Open a row to compare it
   with the source cells (or the screenshot / page, click to zoom), fix anything, or pick the product a
   possible match belongs to.
5. **Commit** applies everything in one go; **Revert** undoes the latest import exactly.

Without an AI key, spreadsheets can still be imported: **Map columns by hand** on a sheet, pick the
title row, the name, price, ERP code … columns and the category, and the rows go to the same review.

### Making a quote

1. Settings → General: upload the logo; fill the bank details, seller contact and signature (printed
   on proforma invoices) when you have them.
2. Customers: add the customer (code such as `SP002`, contact, email, trade term, optional margin).
3. Quotes → **New quote**: pick the customer and the table layout, **Offer** (NO / Name /
   Description, like the UPS offer) or **Quotation list** (specs, model, material, photos, like the
   2-in-1 laptop list). Each table can switch layout, and a quote can hold several tables (options).
4. Add products by searching the catalog (name, ERP code, part number) or items by hand. Quantity,
   cost, margin and unit price edit inline; typing a unit price overrides cost × margin. Open a line to
   edit its printed name and specs (a spec line starting with `!` prints in red) and choose photos
   (added on the product page).
5. To sell several parts as one product (a laptop built from CPU, RAM, SSD …), tick their lines and
   **Combine**, or start a **New combined product** and add its parts. The customer sees one row:
   the name, the parts listed as its description, the photo and one price. You keep the parts and
   their costs. **Split** turns it back into separate lines.
   To reuse a build, save it under **Configurations** (or click the save icon on a combined line).
   **Insert configuration** adds it to any quote at today's catalog prices, with its photos, model
   no. and margin. Each part prints as one description line; tick **Red** to print it in red.
6. **Customer version** shows the PDF to send: products, photos and prices only. **Internal (costs)**
   shows your own copy with the cost, margin and profit of every line. **Download** gives either one
   as PDF or Excel (live formulas). Only a draft changes: once *sent*, make a **New revision**
   (`WKZ…-01 R2`).
7. Mark the quote **Accepted** → **Create proforma invoice** from the lines the customer took, add the
   P.O. number, FOC % and freight, check the terms, then **Issue** it (an issued invoice never changes;
   **New revision** makes `…-R2`).

## Run it

**Windows desktop build (no Python needed):** download `QuoteDesk-windows` from GitHub
(**Actions → Desktop build**, run it or push a `v*` tag), unzip, double-click `QuoteDesk.exe`. The
`data` folder is created next to it. To build it yourself, run `scripts\build-desktop.bat` on Windows
(`scripts/build-desktop.sh` builds the same folder for macOS or Linux).

**From the source:**

You need **Python 3.11+**. The first run also needs **Node.js 20+** to build the interface (later
releases will ship it prebuilt).

| | |
|---|---|
| Windows | double-click `start.bat` |
| macOS / Linux | `./start.sh` |

The first run creates `.venv/`, installs dependencies and builds the UI; later runs start right away.
The app opens at <http://127.0.0.1:8765>. It only listens on this computer: there is no login, so it
is never exposed to the network.

### 运行方法

需要 **Python 3.11 以上**。首次运行还需要 **Node.js 20 以上** 来构建界面。

- Windows：双击 `start.bat`
- macOS / Linux：运行 `./start.sh`

首次运行会自动创建虚拟环境、安装依赖并构建界面，之后会直接启动。浏览器会打开 <http://127.0.0.1:8765>。
程序只在本机监听，不会暴露到局域网。

## Your data

Everything lives in `data/` (git-ignored; in the desktop build, next to `QuoteDesk.exe`):

| Path | Contents |
|---|---|
| `data/app.db` | SQLite database |
| `data/settings.json` | Settings edited in the app |
| `data/.env` | AI provider keys, `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` (never sent to the browser) |
| `data/backups/` | Database copies (one at every start, newest 30 kept), manual and full backups |
| `data/imports/`, `data/exports/` | Uploaded price lists, generated quotes |
| `data/images/` | Product photos, logo, signature |
| `data/logs/app.log` | Rotating log |

Settings → Backups creates, downloads, uploads and restores backups. A restore first saves the
current database as `before-restore-….db`. A full backup (zip) adds photos, uploaded files and
settings, but never `data/.env`. Set `QUOTEDESK_DATA_DIR` to keep the data somewhere else.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd frontend && npm install && cd ..

# API with auto-reload on :8765 (runs migrations + seed on start)
cd backend && ../.venv/bin/python -m app --reload

# UI with hot reload on :5173, proxying /api to :8765
cd frontend && npm run dev
```

Or run both with `docker compose up` (development only; ports are published on 127.0.0.1).

Checks (the same ones CI runs):

```bash
cd backend && ../.venv/bin/pytest -q && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check . && ../.venv/bin/mypy
# live golden tests against the real model (costs a little); runs once per key given
cd backend && QUOTEDESK_LIVE=1 ANTHROPIC_API_KEY=sk-ant-... ../.venv/bin/pytest -m live -q
cd backend && QUOTEDESK_LIVE=1 GEMINI_API_KEY=AIza... ../.venv/bin/pytest -m live -q
cd backend && QUOTEDESK_LIVE=1 GROQ_API_KEY=gsk_... ../.venv/bin/pytest -m live -q
cd frontend && npm run lint && npm run typecheck && npm run build
```

API docs: <http://127.0.0.1:8765/docs>.

### Layout

```
backend/app/
  api/            REST routers under /api/v1
  models/         SQLAlchemy models (Money = exact decimal stored as text)
  schemas/        Pydantic DTOs
  services/
    importer/normalize.py   value normalization + product fingerprint (pure, unit-tested)
    importer/extract_xlsx.py  sheet grid, merged-cell fill, header + metadata, chunks
    importer/extract_media.py screenshots and PDF pages: summaries, numbered text, page renders
    importer/llm_parser.py  model call (Claude, Gemini or Groq): prompt, JSON schema, retries
    importer/matcher.py     normalize + match an extracted row (ERP > MPN > fingerprint > fuzzy)
    importer/pipeline.py    upload, background extraction, analysis
    importer/mapping.py     manual column mapping (import without the AI)
    importer/commit.py      commit and revert
    quotes.py, proformas.py pricing (margin chain), numbering, snapshots, warnings, PI rules
    configurations.py       saved builds: live part prices, insert into quotes, where used
    dashboard.py            dashboard widgets
    documents/              quote and proforma PDF (fpdf2) and Excel (openpyxl) layouts,
                            and the internal cost version (internal.py)
    images.py               uploaded photos, logo, signature
    backup.py               startup, manual and full backups; restore
    catalog.py              product writes, prices, merge
    search.py               FTS5 (trigram) product search
    brands.py, notes.py     brand alias resolution, remark → flag rules
  seed.py         categories + attribute schemas, brands + aliases, remark rules
  assets/fonts/   Noto Sans SC (CJK) embedded in PDFs, see its README
backend/alembic/  migrations
backend/packaging/  PyInstaller spec and entry point of the desktop build
backend/tests/    pytest; fixtures/ holds the sample price lists, screenshots and PDF
frontend/src/     React + Ant Design; i18n/en.json and i18n/zh.json
scripts/          build-desktop.sh / .bat
docs/             plan, sample documents, install guides (INSTALL.md, INSTALL.zh-CN.md)
```

### Adding a migration

```bash
cd backend && ../.venv/bin/alembic revision --autogenerate -m "describe change"
```

Autogenerate renders the `Money` type as `app.models.base.Money`; change it to `sa.String(length=32)` in
the generated file, as `0001` does.
