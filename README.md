# CTI Analyst Copilot

AI-Assisted Threat Information Triage, Research, and Intelligence Analysis



## The Problem

Cyber Threat Intelligence (CTI) analysts receive large volumes of external threat reports from vendors, security researchers, government sources, ISACs, and other intelligence sources. These reports contain potentially valuable threat information, but they are not yet organization-specific intelligence.

Analysts must determine which reports are relevant to their organization, extract important threat data, investigate and enrich artifacts across multiple tools, and correlate the resulting evidence before they can focus on deeper analysis and produce finished intelligence.

This process is often manual, fragmented, and time-consuming. Analysts may need to move between threat intelligence platforms, external enrichment services, and internal security telemetry while processing a single report.

The CTI Analyst Copilot aims to reduce this processing and research burden so analysts can spend more time on intelligence analysis and support teams such as Incident Response, Detection Engineering, and Threat Hunting.

## What It Does

The CTI Analyst Copilot assists analysts through several stages of the threat intelligence workflow.

1. Relevance Assessment

The system evaluates incoming threat reports against predefined organizational context, including:

Priority Intelligence Requirements (PIRs)

Intelligence requirements

Technology exposure

Industry and sector

Geographic exposure

Threat actor priorities

Risk and relevance criteria

It returns an explainable relevance assessment indicating whether the report warrants further analyst attention and why.

2. Threat Information Processing

For relevant reports, the system uses structured LLM outputs to identify and organize important data points such as:

Threat actors and campaigns

Malware

Vulnerabilities and CVEs

MITRE ATT&CK TTPs

Domains, IP addresses, URLs, and file hashes

Adversary infrastructure

Victimology and targeting information

Potential detection opportunities

Potential threat-hunting opportunities

The goal is to transform unstructured reporting into structured threat information that can support further investigation.

3. Artifact Research and Enrichment

Analysts can select extracted artifacts for further investigation.

An agentic workflow can query external threat intelligence sources such as VirusTotal and other enrichment services to gather additional evidence and identify relationships or useful investigative pivots.

The system can also search internal SIEM telemetry to determine whether indicators or related activity from the report have been observed within the organization's environment.

4. Evidence Correlation and Analysis Support

The system combines the original report, extracted threat information, external enrichment, internal telemetry, and relevant organizational context to provide the analyst with an evidence-supported view of the threat.

This can help identify:

Relevant internal activity

Relationships between indicators and infrastructure

Detection opportunities

Threat-hunting opportunities

Potential intelligence gaps

Areas requiring deeper investigation

The system can assist in preparing an initial analytical assessment, but the analyst remains responsible for validating the evidence, applying analytical judgment, determining confidence, and producing the final intelligence product.

Core Principle: Information Is Not Intelligence

A key design principle of this project is maintaining the distinction between collected threat information and finished intelligence.

External reports, indicators, TTPs, enrichment results, and SIEM hits are treated as information and evidence. They become organization-specific intelligence only after they have been evaluated, contextualized, analyzed, and assessed against the organization's intelligence requirements.

The CTI Analyst Copilot therefore aims to assist the intelligence lifecycle rather than replace the intelligence analyst.

## Setup

1. Install uv if you don't have it yet: https://docs.astral.sh/uv/getting-started/installation/

2. Clone this repository (or download the zip and extract it).

3. Create a `.env` file from the template and add your API key:

       cp .env.example .env

4. Install dependencies:

       uv sync

5. Start Jupyter:

       uv run jupyter notebook

## Notebooks

- `notebooks/01-setup.ipynb` - smoke test that confirms your environment works
- `notebooks/02-rag.ipynb` - a minimal RAG baseline you can adapt to your own data

## Data

Put your project data in the `data/` folder. See `notebooks/02-rag.ipynb` for how to load it.
