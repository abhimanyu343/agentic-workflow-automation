# Agentic Workflow Automation

> Business process automation using n8n orchestration + LangChain agents — email triage, CRM updates, report generation, Slack alerts, and data pipelines on autopilot.

![n8n](https://img.shields.io/badge/n8n-1.45-red) ![LangChain](https://img.shields.io/badge/LangChain-0.2-green) ![Python](https://img.shields.io/badge/Python-3.11-blue) ![Docker](https://img.shields.io/badge/Docker-ready-blue)

## Overview

Built from real freelance automation work for SME clients — CRM systems, sales apps, and automated BI dashboards that previously took hours now run unattended. This repo packages the core agent patterns as reusable, production-ready components.

## Workflows Included

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `email_triage` | New email | Classifies, prioritises, drafts reply, routes to team |
| `crm_sync` | Form submission | Enriches lead data, updates CRM, assigns owner |
| `report_generator` | Schedule (daily/weekly) | Pulls data, builds PDF report, emails stakeholders |
| `slack_alert` | Metric threshold breach | Detects anomaly, posts formatted Slack alert |
| `data_pipeline` | File drop / webhook | Cleans, transforms, loads to DB, triggers dashboard refresh |

## Architecture

```
Trigger (webhook / schedule / file watch)
        │
        ▼
   n8n Orchestrator
        │
   ┌────┴────────────────┐
   │                     │
LangChain Agent    Direct API calls
(reasoning tasks)  (CRUD, transforms)
   │
   ├── Tool: Web search
   ├── Tool: Database query
   ├── Tool: Email send
   ├── Tool: Slack post
   └── Tool: PDF generator
        │
        ▼
   Action executed + logged
```

## Quick Start

```bash
git clone https://github.com/abhimanyu343/agentic-workflow-automation
cd agentic-workflow-automation

# Start n8n + agent service
docker-compose up --build

# n8n UI available at: http://localhost:5678
# Agent API at: http://localhost:8001

# Import workflows
python scripts/import_workflows.py
```

## Configuration

Copy `.env.example` to `.env` and fill in:

```
OPENAI_API_KEY=
SLACK_BOT_TOKEN=
SMTP_HOST=
DATABASE_URL=
N8N_WEBHOOK_URL=
```

---
*[LinkedIn](https://linkedin.com/in/abhimanyusarda343) · Built from client automation work (2025–present)*
