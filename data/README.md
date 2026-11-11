# CTI report corpus

`threat_reports.json` now contains **13 public advisories**: the original three
CISA report snapshots from **2026-10-08**, plus **10 official PDF snapshots**
downloaded from FBI IC3 on **2026-11-11**. The original three records are unchanged. Navigation, related-advisory cards, and page
footers were excluded. HTML tables are flattened to text; consult the original
report before relying on indicator-to-field or technique-to-ID associations.
These are historical reports, not a live feed or a current indicator database.

| Report | Publication date | Source |
| --- | --- | --- |
| AA24-038A: PRC State-Sponsored Actors Compromise and Maintain Persistent Access to U.S. Critical Infrastructure | 2024-02-07 | https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a |
| AA23-144A: People's Republic of China State-Sponsored Cyber Actor Living off the Land to Evade Detection | 2023-05-24 | https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-144a |
| AA23-158A: #StopRansomware: CL0P Ransomware Gang Exploits CVE-2023-34362 MOVEit Vulnerability | 2023-06-07 | https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-158a |

The title and publication date in each JSON record come from its source page;
the body may include later revisions. Each record has `report_id`, `title`,
`publisher`, `published`, `source_url`, and `content`. The notebook creates
3,000-character chunks with 500 characters of overlap and retains these fields
plus a stable `chunk_id` consisting of the report ID and character offset.
No model-generated summaries or fabricated threat facts are in this corpus.

`organization_profile_water_utility.json` preserves the original **synthetic** US water utility profile with
PIRs, technology exposure, geography, sector, risk criteria, and explicit unknowns.
Replace it with your organization's approved requirements before real use.
It contains no real customer details or internal telemetry.

Run `notebooks/02-rag.ipynb` from the repository root or `notebooks/` directory.
Loading and retrieval use the local files without network access. An enabled
`rag(...)` call requires `OPENAI_API_KEY` in the environment or the repository's
gitignored `.env` and sends the question, active synthetic profile, and retrieved public
chunks to OpenAI. No external enrichment or SIEM connectors are implemented.

Other realistic data options are MITRE ATT&CK's downloadable STIX objects
(https://attack.mitre.org/resources/attack-data-and-tools/) for structured
enrichment, or clearly labeled synthetic reports and SIEM events for testing
workflow behavior. Neither substitutes for public report evidence in this corpus.

## Chemical manufacturer triage profile

The active `organization_profile.json` now describes **RheinChem Specialty Chemicals
GmbH**, a fictional German chemical manufacturer with 17 PIRs. All company details,
technology assumptions, and two incident-history fixtures are synthetic. The earlier
US water utility profile is preserved as `organization_profile_water_utility.json`.

`risk_matrix.json` defines nine criteria totaling 100 weight points, 0–4 ratings,
unknowns, P1–P5 thresholds, and immediate-review triggers. These are proposed project
defaults, not a validated probability model or an industry scoring standard. Unknown
criteria contribute a range, not an assumed zero. Publication dates do not establish
current targeting or exploitation. The original three CISA records remain unchanged; the corpus has been expanded as described below.

Background guidance informing the proposed focus on safety, operations, and exposure:
- BSI ICS Security Compendium: https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/ICS/ICS-Security_compendium.html?nn=128768
- Chemical Sector Cybersecurity Framework Implementation Guidance: https://www.cisa.gov/sites/default/files/c3vp/framework_guidance/chemical-framework-implementation-guide-2015-508.pdf

The matrix, exact weights, thresholds, and company profile are authored project
assumptions, not values prescribed by these sources.

## Readable evidence citations

Chunking now retains recognized headings from the saved advisory text as
`section_headings`, without changing the corpus text, chunk windows, or IDs.
The heading detector uses explicit section labels; it does not reconstruct every
HTML heading or invent anchors. Unrecognized sections are labeled as unavailable.
Analyst-facing evidence cards resolve quotations to their source location and show
report title, publisher, publication date, section heading, exact quotation, and
original report link. Exported handoffs include these records in `analyst_citations`;
internal chunk references remain intact. Both RAG notebooks contain this code inline.

## Ten additional downloaded PDFs — 2026-11-11

CISA advisory pages denied direct access from this environment, so the PDFs were
downloaded from the official FBI IC3 co-publisher. These are historical snapshots,
not guaranteed latest editions. Their scope includes ransomware, identity abuse,
and PLC/OT compromise; not every report establishes chemical-sector targeting.

`published` is the original publication date. `updated`, when present, records the
revision identified in the downloaded document. A URL's date or a PDF's creation
timestamp is not substituted for those dates. In particular, the BlackSuit PDF
lists an August 7, 2024 body update and subsequent IOC refreshes through August 27.

| Report | Original publication | Downloaded revision | Original PDF | Publisher source |
| --- | --- | --- | --- | --- |
| AA24-109A: #StopRansomware: Akira Ransomware | 2024-04-18 | 2025-11-13 | [PDF](source_reports/AA24-109A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2025/251113.pdf) |
| AA24-242A: #StopRansomware: RansomHub Ransomware | 2024-08-29 | Original edition | [PDF](source_reports/AA24-242A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2024/240829.pdf) |
| AA24-131A: #StopRansomware: Black Basta | 2024-05-10 | 2024-11-08 | [PDF](source_reports/AA24-131A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2024/240511.pdf) |
| AA23-320A: Scattered Spider | 2023-11-16 | 2025-07-29 | [PDF](source_reports/AA23-320A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2025/250729.pdf) |
| AA23-319A: #StopRansomware: Rhysida Ransomware | 2023-11-15 | Original edition | [PDF](source_reports/AA23-319A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2023/231115.pdf) |
| AA25-071A: #StopRansomware: Medusa Ransomware | 2025-03-12 | Original edition | [PDF](source_reports/AA25-071A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2025/250312.pdf) |
| AA23-165A: Understanding Ransomware Threat Actors: LockBit | 2023-06-14 | Original edition | [PDF](source_reports/AA23-165A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2023/230614.pdf) |
| AA23-136A: #StopRansomware: BianLian Data Extortion Group | 2023-05-16 | 2024-11-20 | [PDF](source_reports/AA23-136A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2024/241120.pdf) |
| AA23-335A: IRGC-Affiliated Cyber Actors Exploit PLCs in Multiple Sectors, Including US Water and Wastewater Systems Facilities | 2023-12-01 | 2024-12-18 | [PDF](source_reports/AA23-335A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2023/231201.pdf) |
| AA23-061A: #StopRansomware: BlackSuit (Royal) Ransomware | 2023-03-02 | 2024-08-27 | [PDF](source_reports/AA23-061A.pdf) | [FBI IC3](https://www.ic3.gov/CSA/2024/240807.pdf) |

### How the PDFs enter the notebook

1. Original files are in `source_reports/` (10 PDFs, about 7.4 MB combined).
2. `report_sources.json` records curated titles, dates, and download URLs.
3. `scripts/ingest_report_pdfs.py` uses **pypdf** to extract each page's text,
   trim outer whitespace, and join pages without generating summaries or claims.
4. `source_reports/manifest.json` records PDF SHA-256 hashes, extracted-content
   hashes, sizes, page counts, and page-to-character offsets. Matching `.txt`
   snapshots let analysts inspect the extraction.
5. The extracted records append to `threat_reports.json`, used by the existing
   notebooks, retrieval functions, and agent course exercises.

Extraction does not perform OCR, reconstruct table relationships, or validate
indicator semantics. Inspect the PDF before relying on hashes, CVE/technique
associations, or other fields split across table cells and lines. Existing report
text and chunk IDs remain stable. The expanded dataset produces **242 chunks**
with the unchanged 3,000-character / 500-overlap settings.

Rebuild from saved PDFs offline:

```bash
uv run python scripts/ingest_report_pdfs.py
```

An explicit `--download` option fetches the selected official URLs again. If a
publisher file or an existing report differs, the script refuses to overwrite the
snapshot silently. No download or model request occurs in the default offline run.

Reload the notebook's report-loading and indexing cells to use the new corpus.
The three cached assessments cover only the old reports; newly added reports
remain untriaged until you explicitly run model-based triage. This download and
indexing change does not approve, process, or export any report.

## Uniform pipeline for original and added reports

Every source uses the same six required report fields. `validate_reports` applies
that contract before chunking, including nonempty text, unique report IDs, source
URLs, and dates. Optional PDF provenance is retained without changing source text.
Both RAG notebooks contain the same validation and chunking helpers inline.

The indexing cell now prints a per-report audit: exact reconstruction from the
3,000-character/500-overlap chunks, preserved provenance, recognized section
headings, and retrieval through the same global top-five MinSearch search.
All 13 sources are available to `search → build_prompt → llm → rag`, the course
agent's scratch index, and the existing analyst-reviewed workflow. Citation
instructions use quotations and readable sources; revised PDFs also display their
revision date in the evidence cards.

Offline integration tests exercise each new report through retrieval and prompt
construction, then run `rag` with a stub model. They also verify compatibility with
the Pydantic evidence/processing records and enforce the unchanged approval gate.
These tests do not establish the quality of live generated threat assessments.
No automatic triage, extraction, or approval is implied by a successful index audit.
