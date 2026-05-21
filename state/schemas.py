"""
TypedDict state schemas for LangGraph agents.

Each agent has its own State class that is passed between graph nodes.
TypedDict gives us type safety + IDE completion without Pydantic overhead.

Design principles:
- State is immutable per step — nodes return NEW state dicts (LangGraph handles merging)
- All fields have sensible defaults so nodes can be added without breaking existing graphs
- Sensitive data (email body, PII) is never logged — use __repr__ overrides where needed
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime


# ── Email Triage ──────────────────────────────────────────────────────────────

EmailCategory = Literal["support", "sales", "complaint", "billing",
                         "partnership", "spam", "urgent", "other"]
EmailPriority = Literal["critical", "high", "normal", "low"]


class EmailState(TypedDict, total=False):
    """State for the email triage agent."""
    # Input
    email_id:          str
    sender:            str
    subject:           str
    body_preview:      str        # First 500 chars — full body not stored in state
    received_at:       str        # ISO timestamp
    thread_id:         Optional[str]

    # Classification
    category:          EmailCategory
    priority:          EmailPriority
    confidence:        float
    classification_reasoning: str

    # CRM lookup
    crm_contact:       Optional[Dict[str, Any]]
    is_known_customer: bool
    account_value:     Optional[float]

    # Actions taken
    draft_reply:       Optional[str]
    reply_sent:        bool
    routed_to_team:    Optional[str]
    ticket_id:         Optional[str]
    escalated:         bool
    archived:          bool

    # Audit
    processing_steps:  List[str]  # Track which nodes ran
    errors:            List[str]
    completed_at:      Optional[str]
    total_latency_ms:  Optional[float]


# ── CRM Enrichment ────────────────────────────────────────────────────────────

LeadScore = Literal["hot", "warm", "cold", "disqualified"]


class CRMEnrichmentState(TypedDict, total=False):
    """State for the CRM lead enrichment agent."""
    # Input
    lead_id:           str
    raw_name:          str
    raw_email:         str
    raw_company:       Optional[str]
    source:            str  # "website_form", "linkedin", "referral", etc.

    # Enriched data
    full_name:         Optional[str]
    job_title:         Optional[str]
    company_name:      Optional[str]
    company_size:      Optional[str]  # "1-10", "11-50", "51-200", etc.
    company_industry:  Optional[str]
    linkedin_url:      Optional[str]
    phone:             Optional[str]
    location:          Optional[str]
    enrichment_source: Optional[str]  # Which tool enriched this

    # Scoring
    lead_score:        Optional[LeadScore]
    score_points:      int  # 0-100
    score_reasons:     List[str]
    icp_match:         bool  # Ideal Customer Profile match

    # Assignment
    assigned_to:       Optional[str]
    deal_id:           Optional[str]

    # Audit
    processing_steps:  List[str]
    errors:            List[str]


# ── Report Generation ─────────────────────────────────────────────────────────

class ReportState(TypedDict, total=False):
    """State for the automated report generation agent."""
    # Config
    report_type:       str  # "weekly_sales", "monthly_kpi", "custom"
    report_title:      str
    period_start:      str
    period_end:        str
    recipients:        List[str]
    include_sections:  List[str]

    # Data pulled
    raw_data:          Optional[Dict[str, Any]]  # keyed by section name
    data_quality_ok:   bool
    data_warnings:     List[str]

    # Generated content
    insights:          List[str]  # LLM-generated insights
    pdf_path:          Optional[str]
    email_subject:     Optional[str]
    email_body:        Optional[str]

    # Delivery
    email_sent:        bool
    sent_to:           List[str]

    # Audit
    processing_steps:  List[str]
    errors:            List[str]
    generated_at:      Optional[str]


# ── KPI Alert ─────────────────────────────────────────────────────────────────

AlertSeverity = Literal["critical", "warning", "info"]


class KPIAlertState(TypedDict, total=False):
    """State for the KPI anomaly detection and alerting agent."""
    # Metric info
    metric_name:       str
    metric_value:      float
    metric_unit:       str
    threshold_value:   float
    threshold_type:    Literal["above", "below", "change_pct"]
    time_window:       str  # "1h", "24h", "7d"

    # Context
    historical_values: List[float]
    z_score:           Optional[float]
    pct_change:        Optional[float]

    # Diagnosis
    severity:          AlertSeverity
    root_cause_guess:  Optional[str]
    related_metrics:   List[Dict[str, float]]
    recommended_action: Optional[str]

    # Delivery
    slack_sent:        bool
    slack_channel:     Optional[str]
    slack_ts:          Optional[str]  # Slack message timestamp for threading
    email_sent:        bool
    alert_id:          str

    # Audit
    processing_steps:  List[str]
    errors:            List[str]
