# CTI report corpus

`threat_reports.json` contains the advisory body text downloaded from three
public CISA reports on **2026-10-08**. Navigation, related-advisory cards, and page
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

`organization_profile.json` is a **synthetic** US water utility profile with
PIRs, technology exposure, geography, sector, risk criteria, and explicit unknowns.
Replace it with your organization's approved requirements before real use.
It contains no real customer details or internal telemetry.

Run `notebooks/02-rag.ipynb` from the repository root or `notebooks/` directory.
Loading and retrieval use the local files without network access. The final
`rag(...)` call requires `OPENAI_API_KEY` in the environment or the repository's
gitignored `.env` and sends the question, synthetic profile, and retrieved public
chunks to OpenAI. No external enrichment or SIEM connectors are implemented.

Other realistic data options are MITRE ATT&CK's downloadable STIX objects
(https://attack.mitre.org/resources/attack-data-and-tools/) for structured
enrichment, or clearly labeled synthetic reports and SIEM events for testing
workflow behavior. Neither substitutes for public report evidence in this corpus.
