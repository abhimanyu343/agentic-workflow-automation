# ⚡ Agentic Workflow Automation

> Multi-agent business process automation using LangGraph state machines + LangChain tools + n8n orchestration. Automates email triage, CRM enrichment, scheduled report generation, Slack alerting, and data pipeline runs — end to end, unattended.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)
![LangGraph](https://img.shields.io/badge/LangGraph-0.1-1C3C3C)
![LangChain](https://img.shields.io/badge/LangChain-0.2-green)
![n8n](https://img.shields.io/badge/n8n-1.45-red)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)

---

## 🎯 What This Automates

These workflows were originally built for SME clients — a manufacturing company and a commodities trading firm — where manual processes consumed 15–20 hours/week of team time:

| Workflow | Time saved/week | Before → After |
|----------|----------------|----------------|
| Email triage & routing | ~6 hrs | Manual reading → Auto-classify + route in <30s |
| CRM lead enrichment | ~4 hrs | Copy-paste from LinkedIn → Auto-enrich + score |
| Weekly PDF reports | ~5 hrs | Manual Excel → Auto-pull + format + email |
| KPI breach alerts | Reactive | Dashboard check → Real-time Slack alerts |
| Sales data pipeline | ~2 hrs | Manual CSV downloads → Scheduled ETL + load |

---

## 🏗️ Architecture

### Agent Design Pattern: LangGraph State Machines

Each workflow is a **directed graph** where:
- **Nodes** = actions (LLM call, tool use, API call, DB write)
- **Edges** = conditional transitions based on node output
- **State** = typed Python dataclass passed between nodes

This makes agent behaviour **deterministic, inspectable, and testable** — unlike simple chain-of-thought agents that can loop unpredictably.

```
EMAIL TRIAGE AGENT
──────────────────
START
  │
  ▼
[load_email]          Load email content + metadata
  │
  ▼
[classify_intent]     LLM: classify category + urgency (structured output)
  │
  ├─ urgent ──────▶ [escalate_immediately] → Slack DM to manager
  │
  ├─ support ─────▶ [lookup_crm] → [draft_reply] → [send_reply] → [log_ticket]
  │
  ├─ sales ───────▶ [enrich_lead] → [score_lead] → [assign_owner] → [create_deal]
  │
  ├─ spam ────────▶ [archive]
  │
  └─ other ───────▶ [queue_for_human] → [send_ack]
  │
  ▼
END (log to DB)
```

### Why LangGraph over raw LangChain?
- **Cycles**: Some workflows need to loop (retry, ask clarifying question)
- **Branching**: Different email types → completely different action paths
- **Human-in-loop**: Pause at `[queue_for_human]` and wait for approval
- **Persistence**: State checkpointed at each node → resume after crash

---

## 🤖 Agents Included

| Agent | File | Trigger | Description |
|-------|------|---------|-------------|
| Email Triage | `agents/email_triage_agent.py` | New email | Classify → route → draft reply → log |
| CRM Enrichment | `agents/crm_enrichment_agent.py` | New lead | Enrich contact → score → assign |
| Report Generator | `agents/report_agent.py` | Schedule | Pull data → build PDF → email stakeholders |
| KPI Alert | `agents/kpi_alert_agent.py` | Metric breach | Detect anomaly → format → Slack |
| Data Pipeline | `agents/data_pipeline_agent.py` | File drop / cron | Clean → transform → load → validate |

---

## 🚀 Quick Start

```bash
git clone https://github.com/abhimanyu343/agentic-workflow-automation
cd agentic-workflow-automation
pip install -r requirements.txt
cp .env.example .env  # Fill in your API keys

# Run single agent
python agents/email_triage_agent.py --demo

# Start API server (exposes all agents as REST endpoints)
uvicorn api.main:app --port 8002

# Full stack with n8n
docker-compose up --build
# n8n UI: http://localhost:5678

# Import all workflows
python scripts/import_n8n_workflows.py
```

---

## 📁 Project Structure

```
agentic-workflow-automation/
├── agents/
│   ├── base_agent.py               # Abstract base + common tools
│   ├── email_triage_agent.py       # Full email routing state machine
│   ├── crm_enrichment_agent.py     # Lead enrichment + scoring
│   ├── report_agent.py             # Automated report generation
│   ├── kpi_alert_agent.py          # Real-time KPI breach detection
│   └── data_pipeline_agent.py      # ETL pipeline agent
├── tools/
│   ├── email_tools.py              # Gmail/SMTP tool wrappers
│   ├── crm_tools.py                # CRM CRUD operations
│   ├── slack_tools.py              # Slack messaging tools
│   ├── pdf_tools.py                # PDF report builder
│   └── db_tools.py                 # Database read/write tools
├── state/
│   └── schemas.py                  # TypedDict state schemas for LangGraph
├── api/
│   └── main.py                     # FastAPI — trigger agents via REST
├── n8n_workflows/                  # Exportable n8n workflow JSON files
├── tests/
│   ├── test_email_agent.py
│   └── test_crm_agent.py
├── docker-compose.yml
├── .env.example
└── requirements.txt
```
