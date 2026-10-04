# QuoteDesk — Build Plan

> Single-user, local-only web app for one hardware seller at Shenzhen Sixunited Technology.
> It keeps a product catalog whose prices are imported from supplier price lists (Excel / image / PDF),
> and lets the seller build quotations (single parts or full PC / tablet configurations) and export
> them as PDF / Excel in the company's existing format.
>
> This plan supersedes `docs/superpowers/specs/2026-09-03-quotation-system-design.md`.
> Implementation choices made while building are recorded in `DECISIONS.md`.

---

## 0. Decisions already made & assumptions to confirm

### Confirmed by the owner
| # | Decision |
|---|----------|
| Users | One user (the seller). **No login, no roles.** |
| Deployment | Runs **locally on her personal laptop** (assume Windows 10/11; must also run on macOS/Linux for dev). |
| Language | **UI fully bilingual English + Chinese** (switchable). Product data is mostly Chinese; store Chinese + optional English. |
| Import | **AI-assisted parsing with the Claude API** is allowed (API key configured in Settings). |
| Price rule | **The last uploaded document wins.** Current price = price from the most recent import that contained the product. Keep history. |
| Scale | **1,000+ products**, growing with every import. |
| Proforma invoice | QuoteDesk **generates proforma invoices from accepted quotes, in M4** (§5.4). Format reference: `docs/examples/proforma_invoice_ANZX20260914.pdf`. |
| Issuing company | **Only Shenzhen Sixunited.** The example PI was issued by Shanghai ZY Sales; it is a format reference only. One company profile in Settings. |
| Totals | **Every quote table is always summed** with a total row, including tables of alternative builds (e.g. the 2-in-1 quotation list). |

### Assumptions (defaults chosen by the planner — change if wrong)
| # | Assumption | Why |
|---|------------|-----|
| A1 | Imported prices are **reference/cost prices** (`参考价`). The quote sell price = cost × (1 + margin). Margin is configurable globally, per category, per customer, and overridable per line. Setting margin = 0 makes sell price = imported price. | Covers both cases without a schema change. |
| A2 | Quote currency is **USD only**. Sheets priced in RMB are converted with the exchange rate (`汇率`) found in the sheet (or the rate in Settings if none). Original amount + rate are stored. | The sample quotation PDF is in USD; most sheets say `币种:USD`. |
| A3 | Quantity does **not** change unit price automatically. The seller edits the unit price per line if she wants a volume deal. MOQ / max-order notes are shown as warnings. | No tier data in the samples. |
| A4 | `motherboard_cost.xlsx` **is in scope**: each `机型 + SKU` row is imported as a product of category *Motherboard* with price = `TTL` (total). Cost breakdown columns (PCB / Others / SMT) are kept in attributes. | It is the base of a full-PC configuration. |
| A5 | Two quote layouts, both from the same header (§5.3): **Offer** = `docs/examples/offer_ups_WKZ20260811.pdf` (NO / Name / Description / Q'ty / Unit price / Total) and **Quotation List** = `docs/examples/quotation_list_2in1_laptop_WKZ20260817.pdf` (NO / Description / ST Products No. / Material / Photo / Unit price / Quantity / Total). Layout is chosen per section. Exported as PDF and Excel. No email sending in v1. | Matches the documents she sends today. |
| A6 | Offer number format: `WKZ` + `YYYYMMDD` + `-NN` sequence for the day (`WKZ20260811-01`). Prefix editable in Settings. | Sample shows `WKZ20260811`. |
| A7 | Manually entered extra components can be saved to the catalog with a checkbox (default on). | Avoids re-typing next time. |
| A8 | No Docker required for the end user. The app ships as a one-folder install with a `start` script (Python + SQLite + prebuilt frontend). Docker Compose is provided for development only. | Personal laptop. |

---

## 1. What the source data looks like (read this before writing the importer)

The seller receives price lists from colleagues/suppliers every 1–2 weeks. They are **not** standardized. Observed in the samples:

### 1.1 Excel workbooks
* Many sheets per workbook (28 in `motherboard_cost.xlsx`, 13 in `wifi_price_20260929.xlsx`). Some sheets are junk / personal notes (`Sheet7`, `Sheet6`) → **the user must pick which sheets to import**; default-select sheets that look like price tables.
* Header row is on row 1, 2 or 3; a title row above it often contains the exchange rate and currency: `9月汇率：6.71`, `币种:USD`, `12月份汇率：7.01币种:USA`, `汇率：7.26`.
* **Vertical merged cells** carry the group value for several rows (e.g. `LPDDR5/5X-315` spans 5 rows; `大核` spans the whole CPU table; `WIFI5 1T1R` spans brands). Must forward-fill merged values before parsing.
* Several independent tables can be stacked in one sheet (`E BOM大核` has 3 tables side by side: `类型 / 型号 / 美金单项单价` repeated across columns).
* Price columns vary:
  * weekly: `WK7, WK8 … WK13`
  * monthly: `5月, 7月, 8月, 9月价格`
  * dated: `参考价9/19`, `参考价5/9`, `参考价 WK19`
  * two tiers: `10月不报数参考价格` (no forecast) and `10月报数参考价格` (with forecast)
  * unnamed repeated `参考价, 参考价, 参考价` (chronological left→right)
  * **Rule: the right-most dated/labelled price column is the current price**; others are optional history.
* Non-price values in price cells: `-`, `/`, `现询` (ask for quote), `无价格`, `已停产`, `无货无供应`, `停产` → price = NULL and a status flag.
* Identifier columns: `ERP料号` / `料号` / `IP3料号` / `PN` (`E.I.P.0000455`, `E.M.W.0000119`, `E.M.R.0000036`, `E.I.M.0000540`, `E.M.P.0000389`, `E.I.F.0000357`) — unique when present, often blank or `/`. `原厂料号` = manufacturer part number (MPN). Sometimes several ERP codes in one cell separated by `/`.
* Commercial metadata columns: `总库存` (stock), `总实单需求` (firm demand), `实单后库存` (stock after orders, can be negative), `备注` (notes), `使用平台 / 适配平台` (platform), `接口` (interface), `封装` (package), `主控+flash方案` (controller + NAND), `颗粒` (DRAM chip vendor), `wafer`, `制程` (process), TDP (`28W`).
* Motherboard cost sheets: `机型` (model), `SKU`, `料号`, `PCB`, `Others`, `SMT`, `TTL` (= PCB + Others + SMT), `CPU`, `DDR`, `EMMC`, `WIFI`, `配置` (e.g. `8G+256G`), `Type c`, `日期`, `汇率`, `更新汇率`.

### 1.2 Images (screenshots of Excel tables)
Same tables as above but as JPG/PNG — no ERP codes, Chinese headers, merged cells visible, red text for important notes. Parsed with the Claude vision model.

### 1.3 PDF
Supplier quotations (e.g. UPS + batteries + cabinet). Text-based PDF (WPS export). Parsed with text extraction first, falling back to page images for the vision model.

### 1.4 Note keywords → flags (seed list, extendable in Settings)
| Chinese text (regex, case-insensitive) | Flag / field |
|---|---|
| `接单前确认` / `实单前需确认` | `confirm_before_order = true` |
| `已停产` / `停产` / `已发停产通知` | `status = discontinued` |
| `消耗完库存不接` | `status = stock_only` |
| `无货无供应` | `status = no_supply` |
| `供应良好` / `Q4供应良好` | `supply = good` |
| `交期需确认` | `lead_time_confirm = true` |
| `可接单\s*([\d.]+)\s*K?` | `max_order_qty` (3.7K → 3700) |
| `库存可接\s*([\d.]+)\s*(K|pcs)?` | `from_stock_qty` |
| `预付\s*(\d+)%` …`尾款…` | `payment_terms` (store raw text) |
| `新料需验证` / `需验证` / `待验证` | `needs_validation = true` |
| `现询` | `price = NULL`, `quote_on_request = true` |
| `主推` | `recommended = true` |
| `大众市场` | `market = consumer` |
Unmatched notes are kept verbatim in `notes_raw`.

### 1.5 Brand alias seed list (Chinese ↔ English, extendable)
镁光=Micron / 美光=Micron / SpecTek=Micron(SpecTek) / 海力士=SK hynix / 三星=Samsung / 长鑫=CXMT / 长存=YMTC / 紫光=UNIS / 紫光国芯=UniIC / 沃存=Wodposit / 昱联=Asint / 金速=Kingfast / 威刚=ADATA / 金士顿=Kingston / 英睿达=Crucial / 金泰克=Kimtigo / 江波龙=Longsys(Airdisk) / 至誉=Exascend / 登高者=DGZ / 汇钜=HOGE / 金胜维=KingSpec / 凯威=keyway / 赛可驰=SIX / 泽石=Zettastone / 群联=Phison / 佰维=BIWIN / 时创意=SCY / 联芸=Maxio / 慧荣=SMI / 中龙通=CDTech / 妙明智能=MM / 爱联科技=AI-Link / 大为=DW / 瑞芯微=Rockchip / 高通=Qualcomm / 闪迪=SanDisk / 铠侠=Kioxia / 英特尔=Intel / Yemas=Yemas.

---

## 2. Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | **Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2** | Best ecosystem for Excel/PDF/image parsing and the Anthropic SDK. |
| DB | **SQLite** (WAL mode) via SQLAlchemy; FTS5 virtual table for product search | Single user, local, zero setup, 1k–50k rows is trivial. Keep the ORM clean so Postgres is a config change. |
| Parsing | `openpyxl` (xlsx, merged cells), `pdfplumber` (text PDFs), `pypdfium2` (PDF → PNG), `Pillow` | |
| AI | `anthropic` SDK, model configurable; structured output via a tool/JSON schema | Vision for images and PDF pages; text for pre-extracted sheet grids. |
| PDF export | `fpdf2` with bundled **Noto Sans SC** (CJK) font | Pure Python, works on Windows without GTK. (HTML→PDF via WeasyPrint/Playwright is a later option.) |
| Excel export | `openpyxl` | |
| Frontend | **React 18 + TypeScript + Vite**, **Ant Design 5** (`zh_CN` / `en_US` locales, data tables), TanStack Query, `react-i18next` | Data-heavy admin UI; AntD ships Chinese locale out of the box. |
| Packaging | Frontend built to static files and served by FastAPI at `/`. `start.bat` / `start.sh` creates a venv, installs, runs migrations, starts on `http://127.0.0.1:8765`, opens the browser. Optional final step: PyInstaller one-folder build. | No Docker for the end user. |
| Dev | `docker-compose.yml` (api + vite dev server), `pytest`, `ruff`, `mypy`, `eslint`, `prettier` | |

Repository layout:
```
quotedesk/
  backend/
    app/
      main.py            # FastAPI app, static serving, startup (migrate, backup)
      config.py          # Settings from data/settings.json + .env (API key)
      db.py              # engine/session
      models/            # SQLAlchemy models (one file per aggregate)
      schemas/           # Pydantic DTOs
      api/               # routers: products, categories, imports, quotes, customers, configs, settings, export
      services/
        importer/        # pipeline: extract -> normalize -> match -> review -> commit
          extract_xlsx.py
          extract_pdf.py
          extract_image.py
          llm_parser.py  # Claude calls + JSON schema
          normalize.py   # units, brands, fingerprint
          matcher.py     # erp/mpn/fingerprint/fuzzy
          commit.py
        pricing.py       # margin resolution, totals
        quote_pdf.py     # fpdf2 renderer
        quote_xlsx.py
        search.py        # FTS5
        backup.py
      i18n/              # backend message catalogs (en.json, zh.json)
    alembic/
    tests/
      fixtures/          # the sample files below + expected JSON
    requirements.txt
  frontend/
    src/
      pages/ (Products, ProductDetail, Imports, ImportReview, Quotes, QuoteBuilder, Customers, Configurations, Settings, Dashboard)
      components/
      i18n/ (en.json, zh.json)
      api/ (generated from OpenAPI or hand-written client)
  data/                  # runtime: app.db, imports/, exports/, backups/, settings.json  (git-ignored)
  fonts/NotoSansSC-Regular.otf
  docker-compose.yml
  start.bat  start.sh
  README.md
```

---

## 3. Data model

All tables have `id` (integer PK), `created_at`, `updated_at`. Money columns are `NUMERIC(12,4)` stored as string/Decimal (never float). Dates are ISO.

### 3.1 `categories`
| column | notes |
|---|---|
| `code` (unique) | `cpu, gpu, motherboard, ram_module, dram_chip, ssd, hdd, emmc, psu, wifi, display, battery, camera, cooling, case, keyboard, adapter, cable, ups, cabinet, service, other` |
| `name_en`, `name_zh` | |
| `is_main` | true = main component (CPU, GPU, motherboard, RAM, SSD, HDD, eMMC, PSU, WiFi, display). false = extra. |
| `attribute_schema` JSON | ordered list of `{key, label_en, label_zh, type, unit, in_fingerprint: bool}` — see §3.3 |
| `default_margin_pct` | nullable; overrides global |
| `sort_order` | |
Seeded on first run; editable in Settings.

### 3.2 `products`
| column | notes |
|---|---|
| `category_id` FK | |
| `erp_code` | nullable, **unique when not null** (e.g. `E.M.R.0000036`). Multiple codes in source (`A/B/C`) → first one here, the rest in `erp_code_alt` JSON. |
| `mpn` | manufacturer part number (`原厂料号`), nullable, indexed |
| `name_zh` | required. Display name, built from source (`DDR4 8GB 2666MHZ 沃存 海力士颗粒 SO-DIMM`) |
| `name_en` | nullable; auto-translated by the LLM at import (flag `name_en_auto = true`) and editable |
| `brand_id` FK → `brands` | nullable |
| `attributes` JSON | per-category structured fields, validated against `category.attribute_schema` |
| `fingerprint` | **unique**, see §3.4 |
| `current_price_usd` | denormalized from latest `price_history` |
| `current_price_tier_forecast_usd` | nullable second tier (`报数` price) |
| `price_date` | date from the source document (or import date) |
| `last_import_id` FK | |
| `status` | `active / discontinued / stock_only / no_supply / inactive` |
| `confirm_before_order`, `lead_time_confirm`, `needs_validation`, `quote_on_request`, `recommended` bool | |
| `stock_qty`, `demand_qty`, `stock_after_qty` int nullable | |
| `max_order_qty`, `from_stock_qty` int nullable | |
| `payment_terms` text nullable | |
| `supply_note` text nullable | e.g. `Q4供应良好` |
| `notes_raw` text | verbatim remarks from source |
| `platform` text nullable | `X86 / Intel/AMD / 龙芯 / ARM` |
| `is_manual` bool | created by hand in a quote |
| `description_zh`, `description_en` | optional long text used on quotes |
FTS5 table `products_fts(name_zh, name_en, erp_code, mpn, brand, attributes_text)`.

### 3.3 Attribute schemas (seed)
* **ram_module**: `type` (DDR3/DDR4/DDR5/LPDDR4X/LPDDR5/LPDDR5X)*, `capacity_gb`*, `speed_mhz`*, `form_factor` (SODIMM/UDIMM/SO-U)*, `chip_vendor`* (颗粒), `rank`, `voltage`.
* **dram_chip**: `type`* (e.g. `LPDDR5/5X-315`), `capacity_gb`*, `speed_mhz`*, `package_balls`*, `wafer_vendor`*, `platform`.
* **ssd**: `capacity_gb`*, `form_factor`* (2280/2242/2230), `interface`* (SATA/PCIe3.0/PCIe4.0), `nand_type` (TLC/QLC)*, `controller`, `nand_vendor`, `solution_text` (方案 verbatim), `full_capacity` (足容), `fixed_firmware` (固带).
* **emmc**: `capacity_gb`*, `controller_nand`*, `firmware` (Intel FW / ARM FW).
* **cpu**: `model`* (`i5-1340P`), `sspec` (`SRMJ7`), `platform_family`* (Raptor Lake-P), `tdp_w`, `process_nm`, `vpro`, `ipu`, `core_class` (大核/小核).
* **wifi**: `chipset`* (`AX211`, `RTL8821CE`), `module_model`* (`AX211.D2WG.NV,999M5T`), `interface`* (CNVi/PCIe/USB), `package` (插卡/贴片), `wifi_gen` (WIFI5/WIFI6/WIFI7), `streams` (1T1R/2T2R), `vendor_module`.
* **motherboard**: `model`* (机型 `XN21S`), `sku`* (`SKU12`), `erp_code` (料号), `pcb_spec` (`10L+HDI2+OSP`), `cpu`, `memory_config` (`8G+256G`), `typec`, `wifi`, `cost_pcb`, `cost_others`, `cost_smt`, `cost_ttl`, `fx_rate`.
* **ups / battery / cabinet / other extras**: `model`*, `spec_text` (free), `power_va`, `power_w`, `capacity_ah`, `size_mm`, `weight_kg`.
(`*` = part of the fingerprint.)

### 3.4 Uniqueness — the fingerprint
```
fingerprint = sha1(category.code + "|" + brand.canonical + "|" + join("|", normalized(attr[k]) for k in schema where in_fingerprint, in schema order))
```
Normalization (`normalize.py`, fully unit-tested):
* lowercase, strip, collapse whitespace, full-width → half-width punctuation (`（）` → `()`, `，` → `,`);
* capacities `8GB / 8G / 8 GB / 8g` → `8`; `1T / 1TB` → `1024`; `512M` → `0.5`;
* frequencies `2666MHZ / 2666 MHz / 2666` → `2666`;
* `SO DIMM / SODIMM / SO-DIMM` → `sodimm`; `SO/U DIMM` → `so_u_dimm`;
* interface `PCIE3.0 / PCIe 3.0 / PCIE3` → `pcie3`;
* brand → canonical via `brands`/`brand_aliases` (Chinese or English input both resolve).
Two RAM modules with the same type/capacity/speed/form factor but different brand or chip vendor → different fingerprints → different products (required by the owner).
**Uniqueness precedence on import (matcher.py):**
1. `erp_code` exact → same product (even if fingerprint changed: update attributes, log a warning in review).
2. `mpn` exact within the same category.
3. `fingerprint` exact.
4. Fuzzy: trigram similarity on `name_zh` ≥ 0.85 **and** same category → shown as *"possible match"* in review, user decides (merge / create new).
5. Otherwise → new product.
A `merge_products(keep_id, drop_id)` admin action moves price history, quote lines and aliases, and records `product_aliases(dropped_fingerprint → keep_id)` so the next import resolves automatically.

### 3.5 `brands` / `brand_aliases`
`brands(id, canonical, name_en, name_zh)`, `brand_aliases(brand_id, alias, lang)`. Seeded from §1.5; any unknown brand string at import is created and flagged for review.

### 3.6 `price_history`
| column | notes |
|---|---|
| `product_id` FK, `import_id` FK nullable (null = manual edit) | |
| `price_usd`, `tier` (`standard` / `forecast`) | |
| `amount_original`, `currency_original`, `fx_rate` | e.g. 14.85 CNY @ 6.7175 |
| `price_date` | parsed from column header / sheet title / file name (`wifi_price_20260929`) / import date |
| `source_ref` | `wifi_price_20260929.xlsx!domestic WIFI!K3` or `image.jpg row 3` |
| `is_current` | exactly one current row per (product, tier) |
"Last upload wins": on commit, the row from the newest import becomes current regardless of `price_date`; a warning is shown in review if the new `price_date` is older than the current one.

### 3.7 `imports` / `import_rows`
`imports(id, filename, stored_path, file_type xlsx|image|pdf, sheets_selected JSON, status uploaded|extracting|review|committed|failed|cancelled, llm_model, llm_tokens_in, llm_tokens_out, stats JSON {new, updated, unchanged, skipped, errors}, started_at, committed_at, error)`.
`import_rows(id, import_id, row_index, sheet, source_ref, raw JSON, parsed JSON, match_type erp|mpn|fingerprint|fuzzy|new, matched_product_id, candidates JSON, decision create|update|skip|merge_into, user_edits JSON, confidence float, issues JSON[])`.
Original files are stored under `data/imports/<import_id>/`.

### 3.8 `customers`
`code` (unique, e.g. `SP002`), `name`, `contact_name`, `email`, `phone`, `address`, `trade_term` (FOB Shenzhen / EXW / CIF …), `payment_terms`, `default_margin_pct` nullable, `notes`, `language` (en/zh for the quote document).

### 3.9 `quotes` / `quote_sections` / `quote_lines`
`quotes(id, offer_no unique, revision int, parent_quote_id, status draft|sent|accepted|lost|expired, offer_date, valid_until, customer_id, customer_snapshot JSON, contact, trade_term, currency 'USD', language en|zh, notes_header, notes_footer, subtotal, discount_pct, discount_amount, grand_total)`.
`quote_sections(id, quote_id, title, sort_order, subtotal)` — one section = one option table on the PDF (the sample has 2).
`quote_lines(id, section_id, sort_order, line_no, kind product|manual|config, product_id nullable, configuration_id nullable, name, description, qty, cost_usd, margin_pct, unit_price (editable), total (= qty × unit_price), price_source {product_price_date, import_id}, warnings JSON, breakdown JSON for config lines, show_breakdown bool)`.
Snapshots: line `name/description/cost/unit_price` are **copied** at insert time; later price changes never alter a quote. Dashboard shows "open quotes with lines whose product price changed since".

### 3.10 `configurations` (reusable PC / tablet builds)
`configurations(id, name, name_zh, description, platform, base_margin_pct)`; `configuration_items(configuration_id, product_id nullable, manual_name, manual_cost, qty, role cpu|motherboard|ram|ssd|wifi|extra|service, sort_order)`.
Price is always recomputed from current product prices when inserted into a quote (with a diff warning vs. last saved total).

### 3.9a Quote additions for the example layouts
* `quotes`: `contact_email` (shown as `Email:` in the header), `validity_days` (printed as `Valid: 7 Days`; `valid_until` = offer date + days), `trade_term` holds incoterm + place (`FOB Shenzhen`, `FOB Huai'nan`).
* `quote_sections.layout`: `offer` | `list` (§5.3).
* `quote_lines`: `model_no` (ST Products No., e.g. `DN11-116PC-HS-R52`), `material` (e.g. `Plastic`), `image_ids` JSON (photos printed in the Photo column), `description_lines` JSON — ordered list of `{text, emphasis: bool}`. Emphasized lines print in red; the sample uses this to point out what differs between builds (CPU, screen resolution, `全新`/`二手` RAM).
* `products` and `configurations` gain `model_no`, `material`, and images (`product_images(product_id|configuration_id, path, sort_order)`, files under `data/images/`). They are copied onto the line when inserted.
* Component condition: RAM/SSD lines may be new (`全新`) or used (`二手`). Store as an attribute `condition` (`new` | `used`) on configuration items; it is part of the generated description.

### 3.11 `settings` (single JSON document in `data/settings.json`, edited from the UI)
company (name en/zh, address, logo path, phone, email; **bank**: account name, account no., bank name, SWIFT; **seller contact**: name, phone, email, signature image path), PI defaults (`pi_prefix` e.g. `ANZX`, payment-term template, lead-time days, delivery place text, warranty months), `offer_prefix` = `WKZ`, `default_margin_pct`, `default_fx_rate_cny_usd`, `default_validity_days` = 30, `anthropic_api_key` (stored in `.env`, never returned to the UI after save), `llm_model`, `ui_language`, `pdf_show_cost_breakdown` default false, `rounding` (2 decimals), backup retention.

---

## 4. Import pipeline (the core feature)

### 4.1 Flow (UI: Imports page → New import wizard)
1. **Upload** one or more files (`.xlsx .xls .csv .png .jpg .jpeg .pdf`). Multiple images selected together = one import.
2. **Pre-extraction** (no AI yet):
   * xlsx: list sheets with row count and a "looks like a price table" heuristic (has a header cell matching `价|price|参考|报价|WK\d+|\d+月`). Pre-select those. Render a 15-row preview per sheet.
   * pdf: page count + text preview; if text is empty → mark as scanned (vision path).
   * image: thumbnail.
3. **Sheet / page selection** + category hint per sheet (optional dropdown: "this sheet contains: RAM modules / CPUs / …" — the LLM gets it as a hint, can still override per row).
4. **Extraction** (background task, progress bar):
   * xlsx → for each selected sheet: forward-fill merged cells, drop fully empty rows/cols, detect header row(s), find title-row metadata (fx rate, currency, month), slice into chunks of ≤ 60 data rows (header repeated in every chunk), send each chunk to Claude as a Markdown/TSV grid with cell references (`A3`), plus the category hint, plus the category attribute schemas, and ask for structured rows.
   * image → send the image to Claude (vision) with the same schema.
   * pdf → text layer via pdfplumber if present (send text with layout), else render pages at 150 dpi and send as images.
   * Response schema (enforced with a tool definition / JSON schema):
     ```json
     { "sheet_meta": {"currency":"USD|CNY|null","fx_rate":6.71,"price_date":"2026-09-28","price_tiers":["standard","forecast"]},
       "rows": [{
         "source_ref":"A5:J5", "category_code":"ram_module",
         "erp_codes":["E.M.R.0000036"], "mpn":"WPBH26D408SWA-8G",
         "name_zh":"DDR4 8GB 2666MHZ 沃存 海力士颗粒", "name_en":"DDR4 8GB 2666MHz Wodposit (SK hynix chips)",
         "brand":"沃存(Wodposit)",
         "attributes":{"type":"DDR4","capacity_gb":8,"speed_mhz":2666,"form_factor":"SODIMM","chip_vendor":"海力士"},
         "prices":[{"tier":"standard","amount":14.5,"currency":"USD","date":"2026-09-28","source_ref":"H5"}],
         "no_price_reason":null,
         "stock_qty":null,"demand_qty":null,"stock_after_qty":null,
         "notes_raw":"接单前确认", "platform":"Intel/AMD",
         "confidence":0.92, "issues":["two price columns, took right-most"] }]}
     ```
   * Prompt rules given to the model: take the right-most labelled price as current; `-`/`/`/`现询` → no price; respect merged-cell groups; never invent an ERP code; output Chinese names verbatim; translate `name_en` concisely; map brands to the alias list provided; flag anything ambiguous in `issues`.
   * Each chunk is retried up to 3 times on schema failure; token usage is recorded on the import.
5. **Normalize + match** (deterministic, §3.4): compute fingerprint, resolve brand, apply note-keyword flags (§1.4), convert currency, decide `match_type`, diff against the matched product (price delta %, changed attributes, changed status).
6. **Review screen** (the most important UI in the app):
   * table of rows with status chips: **New** (green), **Updated** (blue, shows `old → new` price with %), **Unchanged** (grey), **Possible match** (orange, pick candidate or "create new"), **Problem** (red: no category, invalid attribute, failed schema).
   * filters by status/sheet/category; inline editing of any parsed field; bulk actions (skip all unchanged, accept all updates, set category for selected rows);
   * large price swings (> ±30%) and price-date-older-than-current are highlighted;
   * the original cell/image region is shown next to the row (xlsx: the raw row values; image: the whole image with the row highlighted if coordinates are available, else just the image).
7. **Commit**: in one transaction create/update products, insert `price_history`, set `is_current`, update denormalized fields, store stats. Import becomes `committed`. Undo = "Revert import" (restores previous current prices, deletes products created by this import that have no quote lines).

### 4.2 Fallback without AI
If no API key is configured (or the call fails), xlsx/csv can still be imported through a **manual column-mapping** dialog (pick header row, map columns to fields, pick the sheet's category). Images/PDF require the API. Build this after the AI path works; keep the same normalize/match/review/commit code.

### 4.3 Golden tests
Put the provided sample files in `backend/tests/fixtures/` and write tests that assert the expected normalized rows for:
* `wifi_price_20260929.xlsx` sheets `Intel wifi`, `domestic WIFI`, `DDR颗粒参考价`, `内存条 参考价`, `SSD`, `EMMC` (expected: ERP codes captured, right-most price, CNY→USD on `domestic WIFI` using 6.7175, merged groups filled);
* `motherboard_cost.xlsx` sheet `DB小板汇总` (model + SKU + TTL, fx 6.71) and that `Sheet7` is not pre-selected;
* the 4 screenshots (RAM chips `LPDDR5/5X-315` group, RAM modules with red payment notes, SSD list with `/` prices and `库存可接1629pcs`, the CPU table with two price tiers and negative stock-after values);
* `Sixunied_UPS_Quotation.pdf` → 6 products in categories `ups / battery / cabinet` with unit prices.
Unit tests for every normalization rule and for fingerprint stability (same product in different spellings → same fingerprint; different brand → different fingerprint).

---

## 5. Quotation builder

### 5.1 Quote list
Search by offer no / customer / status / date; duplicate; new revision; export; mark status.

### 5.2 Builder page (`/quotes/:id`)
* Header form: customer (searchable select, auto-fills code / contact / trade term / payment terms / language), offer date, validity, currency (USD, read-only in v1), language of the document (en/zh), header & footer notes.
* Sections (option tables): add / rename / reorder / delete. Each has its own line table and subtotal.
* **Add line** popover with a fast search box (FTS, matches Chinese, English, ERP code, MPN; filter by category; shows price, price date, status flags, stock). Enter adds the line. Keyboard-first.
* **Add configuration**: pick a saved configuration → inserts one `config` line (name = configuration name, description = component list, unit cost = Σ components) with an expandable breakdown; option to "explode" into individual lines instead.
* **Add manual item**: name, description, cost, qty, category, checkbox "save to catalog" (creates product with `is_manual = true`).
* Line table columns: No., Name, Description (editable, prefilled from attributes/description), Qty, Cost, Margin %, Unit price (editable; editing it recomputes margin), Total, warnings icon (discontinued / confirm before order / no stock / price older than N days / price changed since insert), remove.
* Pricing resolution for a line: `margin = line.margin ?? customer.default_margin ?? category.default_margin ?? settings.default_margin`; `unit_price = round(cost × (1 + margin/100), 2)`; `total = qty × unit_price`; section subtotal, optional global discount, grand total. All Decimal.
* Live totals; autosave (debounced PATCH).
* Actions: Preview PDF, Download PDF, Download Excel, Duplicate, New revision (increments `revision`, offer no becomes `WKZ20260811-01 R2`), Change status.

### 5.3 PDF layout (match the samples in `docs/examples/`)
**Header (both layouts):** logo + company name + address (bilingual if `language = zh`); a two-row grid
`Offer No. | To | Contact | Email` and `Offer date | Client Code | Trade Term | Valid: N Days`
(the UPS sample shows the first three columns only; Email/Valid print when set). Offer date format `DD/MM/YYYY`.

**Section layout `offer`** (UPS sample): `NO | Name | Description | Q'ty | Unit Price($) | Total price($)`, then a highlighted `Total price` row.

**Section layout `list`** (2-in-1 laptop sample): optional table title (`Quotation List`), columns
`NO. | Description | ST Products No. | Material | Photo | Unit Price($) | Quantity | Total Price($)`.
Description is the multi-line spec list (one component or feature per line, emphasized lines in red),
Photo shows up to two product images side by side, rows are tall and never split across pages.
A `Total price` row follows (owner decision: always summed).

Both: amounts `$4,699,746.00` (unit price may print without decimals when whole, as in the sample: `$573`);
footer notes (payment terms, bank info); page numbers. Cost/margin never printed unless
`pdf_show_cost_breakdown` is on. CJK font embedded. Excel export mirrors the same layout with formulas
for totals and embedded photos.

### 5.4 Proforma invoice (from an accepted quote)
Reference: `docs/examples/proforma_invoice_ANZX20260914.pdf` (issued there by another company; QuoteDesk
always issues as Sixunited).
* Action **Create proforma invoice** on an accepted quote. The seller picks which lines/sections to include
  (a quote of alternatives usually becomes a PI for one build) and can edit quantities.
* **Header:** company name + address, title `Proforma Invoice`, customer box (`name`, `Atten:`), and
  `Inv No.` (`pi_prefix` + `YYYYMMDD`, editable), `Date`, `P.O No.` (customer PO, entered by the seller),
  `Customer ID` (customer code), `Contact` + `Phone` (seller contact from Settings), `Currency: USD`.
* **Table:** `Model | Name | Description | Photo | Quantity | Unit Price | Net Amount`; optional
  **FOC** line (`1.5% FOC` = free spare units, percentage of quantity, printed in the description, no
  charge); `Freight` line (amount or blank); `Total`.
* **Terms & conditions** (numbered, prefilled from Settings, editable per PI): 1 Payment term (incoterm +
  `60% deposit by T/T upon confirmation, remaining 40% by T/T prior to shipment`), 2 Lead time
  (`55 working days from receipt of the advance payment`), 3 Delivery place, 4 Warranty (`12 months from
  the date of delivery`).
* **Banking info** (account name, account no., bank name, SWIFT) and **signature blocks**: seller
  (`Signed by:` + signature image + date) and buyer (blank).
* Data: `proforma_invoices(id, pi_no unique, quote_id, po_no, issue_date, customer_snapshot JSON,
  attention, seller_contact JSON, currency, foc_pct, freight, terms JSON, subtotal, total, status
  draft|issued|cancelled)` and `proforma_lines` (snapshot of the chosen quote lines). Once `issued`, a PI is
  immutable; changes create a new PI number (`-R2`).
* Exports: PDF and Excel, like quotes.

---

## 6. Other screens
* **Dashboard**: products count, last import (date, new/updated), open quotes, price changes > 20% in the last import, discontinued products that appear in open quotes, products with price older than 30 days.
* **Products**: AntD table with FTS search, category/brand/status filters, column chooser, inline price edit (creates a manual `price_history` row), product detail with price history chart (simple line), attributes, aliases, quotes that used it, merge-into action, deactivate.
* **Customers**: CRUD.
* **Configurations**: CRUD, component picker, live computed cost, "where used".
* **Settings**: company & PDF header, margins, FX rate, offer prefix, language, API key + model + "test connection" button, categories & attribute schemas editor, brand aliases editor, note-keyword rules editor, backups (list / create / restore).

---

## 7. API (REST, `/api/v1`, OpenAPI docs at `/docs`)
```
GET/POST        /products            ?q=&category=&brand=&status=&page=   (FTS search)
GET/PATCH/DEL   /products/{id}        ; GET /products/{id}/prices ; POST /products/{id}/merge {into_id}
GET/POST        /categories ; PATCH /categories/{id}
GET/POST        /brands ; POST /brands/{id}/aliases
POST            /imports              (multipart) -> {import_id, sheets[]}
POST            /imports/{id}/extract {sheets:[...], hints:{sheet:category}}   -> 202, poll
GET             /imports/{id}         (status, progress, stats)
GET             /imports/{id}/rows    ?status=   ; PATCH /imports/{id}/rows/{row_id} {decision, edits}
POST            /imports/{id}/bulk    {action, row_ids|filter}
POST            /imports/{id}/commit  ; POST /imports/{id}/revert ; DELETE /imports/{id}
GET/POST        /customers ; GET/PATCH/DEL /customers/{id}
GET/POST        /configurations ; GET/PATCH/DEL /configurations/{id}
GET/POST        /quotes ; GET/PATCH/DEL /quotes/{id} ; POST /quotes/{id}/duplicate ; POST /quotes/{id}/revision
POST/PATCH/DEL  /quotes/{id}/sections[/{sid}] ; POST/PATCH/DEL /quotes/{id}/lines[/{lid}] ; POST /quotes/{id}/lines/reorder
GET             /quotes/{id}/export.pdf ; GET /quotes/{id}/export.xlsx
POST            /quotes/{id}/proforma {line_ids, po_no} ; GET/PATCH /proformas/{id} ; POST /proformas/{id}/issue
GET             /proformas/{id}/export.pdf ; GET /proformas/{id}/export.xlsx
POST/DEL        /products/{id}/images ; POST/DEL /configurations/{id}/images
GET/PUT         /settings ; POST /settings/test-llm ; POST /backups ; GET /backups ; POST /backups/{name}/restore
GET             /dashboard
```
Errors: RFC 7807 problem JSON, messages keyed for i18n.

---

## 8. i18n
* Frontend: `react-i18next`, two catalogs `en.json`, `zh.json`, language switch in the top bar, persisted in settings. AntD `ConfigProvider` locale follows it. Every user-visible string goes through `t()` — no hard-coded English in components.
* Data: products show `name_zh` and `name_en` (fallback to `name_zh`); search hits both. Quote document language is per quote (customer default).
* Backend validation / error messages use message keys; the frontend translates.
* Number/date formatting via `Intl` per locale; currency always `$ 1,234.56`.

---

## 9. Local run, packaging, backups
* `start.bat` / `start.sh`: check Python ≥ 3.11, create `.venv`, `pip install -r requirements.txt` (offline-friendly: vendor wheels later), `alembic upgrade head`, start uvicorn on `127.0.0.1:8765`, open the default browser. Logs to `data/logs/app.log` (rotating).
* The server binds to localhost only (no auth, so it must never listen on `0.0.0.0`).
* On startup: copy `app.db` to `data/backups/app-YYYYMMDD-HHMM.db` (keep last 30); manual backup/restore in Settings. Imports folder is included in a "full backup" zip.
* Final milestone: PyInstaller one-folder build (`QuoteDesk/QuoteDesk.exe`) that bundles Python, the backend, the built frontend and the font; the frontend is built in CI (GitHub Actions) and committed as release artifacts.
* `docker-compose.yml` for developers only.

---

## 10. Non-functional requirements
* Product search < 100 ms for 50k products (FTS5 + indexes on `erp_code`, `mpn`, `fingerprint`, `category_id`).
* Import of a 600-row sheet completes in < 2 minutes with the API (chunks run concurrently, max 4 in flight); the UI shows per-sheet progress and can be cancelled.
* All money math in `Decimal`; totals round half-up to 2 decimals at the line level.
* Every write to products/prices is traceable to an import row or a manual edit (audit: `price_history.import_id`, `products.last_import_id`).
* API key only in `.env` with file permissions; never logged; never sent to the browser.
* Works offline except the AI extraction step.

---

## 11. Milestones (each ends with a demo and passing tests)

**M0 — Scaffold (day 1)**: repo layout, FastAPI + SQLite + Alembic, React/Vite/AntD/i18n shell with language switch, `start` scripts, CI running `pytest` + `eslint`. Seed categories, brands, aliases, note rules.

**M1 — Catalog**: products CRUD, FTS search, category attribute schemas, fingerprint + normalization (with unit tests), manual price edit + price history, merge products, brands/aliases editor.

**M2 — Import (xlsx via AI)**: upload → sheet picker → extraction → normalize/match → review screen → commit/revert. Golden tests on the two sample workbooks. Import log + stored files.

**M3 — Import (images + PDF)**: vision path, PDF text/vision path, multi-image import. Golden tests on the 4 screenshots and the UPS PDF.

**M4 — Quotes + proforma invoices**: customers, quote builder (sections with `offer`/`list` layouts, product lines, manual lines, description lines with emphasis, photos, margin resolution, warnings), PDF + Excel export matching both samples in `docs/examples/`, revisions/status, duplicate; proforma invoice from an accepted quote (§5.4) with PDF + Excel export.

**M5 — Configurations + Dashboard**: saved builds, config lines with breakdown, dashboard widgets, "price changed since quote" alerts.

**M6 — Hardening & packaging**: manual column-mapping fallback, backups/restore, settings polish, full zh translation review, PyInstaller build, README with install steps for the seller (screenshots in zh and en).

Out of scope for v1 (keep the schema ready): multi-user/auth, cloud hosting, email sending, ERP integration, multi-currency quotes, quantity-tier pricing, purchase orders, commercial invoices (proforma invoices **are** in scope, §5.4), multiple issuing companies.

---

## 12. Working rules for Claude Code

* Build milestone by milestone, in order. After each milestone run the tests, start the app, and show how to try it.
* Do not add authentication. Keep the server bound to 127.0.0.1.
* All UI strings go through i18n with both `en` and `zh` catalogs.
* Ask only when the plan is contradictory; otherwise choose the simplest option and note it in `DECISIONS.md`.
* Output-format references (what QuoteDesk generates) live in `docs/examples/`: the UPS offer, the 2-in-1
  laptop quotation list, and the proforma invoice.
* Sample files live in `samples/` and are copied to `backend/tests/fixtures/`:
  `motherboard_cost.xlsx`, `wifi_price_20260929.xlsx`, `Sixunied_UPS_Quotation.pdf`,
  `img_dram_chips.jpg`, `img_ram_modules.jpg`, `img_ssd.jpg`, `img_cpu.jpg`.
