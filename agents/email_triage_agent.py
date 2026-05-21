"""
Email Triage Agent — LangGraph state machine for intelligent email routing.

Graph nodes:
  load_email        → normalise raw email into state fields
  classify_intent   → LLM classifies category + priority (structured output)
  lookup_crm        → check if sender is known customer/lead
  route_decision    → conditional edge: which action path to take?
  draft_reply       → LLM drafts appropriate acknowledgement reply
  send_reply        → send via SMTP/Gmail
  escalate          → urgent: DM manager on Slack immediately
  create_ticket     → support/complaint: log in ticketing system
  enrich_lead       → sales: call enrichment API, score lead
  archive           → spam: mark and archive
  queue_for_human   → ambiguous: notify team, add to review queue
  log_outcome       → write final record to DB regardless of path

Conditional routing (route_decision node):
  urgent    → escalate → create_ticket → log_outcome
  support   → draft_reply → send_reply → create_ticket → log_outcome
  sales     → enrich_lead → draft_reply → send_reply → log_outcome
  complaint → draft_reply → send_reply → escalate → create_ticket → log_outcome
  spam      → archive → log_outcome
  other     → queue_for_human → log_outcome
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

log = logging.getLogger(__name__)

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    log.warning("langgraph not installed. Install with: pip install langgraph")

from agents.base_agent import BaseAgent, retry_node, log_step, parse_llm_json
from state.schemas import EmailState, EmailCategory, EmailPriority


CLASSIFICATION_PROMPT = """You are an expert email classifier for a B2B business operations team.

Analyse the following email and classify it. Be precise — your classification directly determines
how the email is handled and how quickly customers get responses.

Email:
From: {sender}
Subject: {subject}
Body (preview): {body_preview}

Classify into EXACTLY one of these categories:
- support: Technical help, how-to questions, product issues, usage questions
- sales: Inquiry about pricing, demo requests, partnership proposals, new business
- complaint: Expressing dissatisfaction, requesting refund, escalating an issue
- billing: Invoice queries, payment issues, subscription changes
- urgent: Contains words like "URGENT", "critical", "system down", "outage", deadline today
- spam: Marketing, newsletters, automated notifications, job postings, irrelevant
- other: Doesn't fit above categories

Priority levels:
- critical: Needs response within 1 hour (outages, legal, major customer complaints)
- high: Needs response within 4 hours (new sales inquiry, billing issue, complaints)
- normal: Needs response within 24 hours (most support, general enquiries)
- low: Needs response within 72 hours (newsletters, low-value enquiries)

Respond with JSON only:
{{
  "category": "<category>",
  "priority": "<priority>",
  "confidence": <0.0-1.0>,
  "reasoning": "<1-2 sentence explanation>",
  "key_entities": ["<product/service/person names mentioned>"],
  "sentiment": "<positive|neutral|negative|very_negative>"
}}"""


REPLY_TEMPLATES = {
    "support": """Thank you for reaching out to our support team.

We've received your enquiry and it has been assigned to our {team} team with reference #{ticket_id}.

Our team will review your request and get back to you within {sla}.

If this is urgent, please reply with "URGENT" in the subject line.

Best regards,
Support Team""",

    "sales": """Thank you for your interest in our solutions!

We've received your enquiry and one of our team members will reach out within 1 business day
to discuss how we can best support your needs.

In the meantime, you might find our resources helpful: [link]

Looking forward to connecting!

Best regards,
{assigned_owner}
Business Development""",

    "complaint": """Thank you for bringing this to our attention.

I sincerely apologise for the experience you've had. This is not the standard we hold ourselves to,
and I want to assure you this will be addressed immediately.

Your case has been escalated to our senior team (reference: #{ticket_id}) and someone will
contact you within 2 hours with a resolution plan.

Best regards,
Customer Success Team""",
}


class EmailTriageAgent(BaseAgent):
    """
    LangGraph-based email triage agent with conditional routing.

    Usage:
        agent = EmailTriageAgent(verbose=True)
        result = agent.run({
            "email_id": "msg_001",
            "sender": "customer@acme.com",
            "subject": "Billing issue with invoice #1234",
            "body_preview": "Hi, I received invoice #1234 but the amount...",
            "received_at": "2026-05-21T10:30:00Z"
        })
        print(result["category"], result["reply_sent"])
    """

    def build_graph(self):
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("langgraph required. pip install langgraph")

        graph = StateGraph(EmailState)

        # Add nodes
        graph.add_node("load_email",      self._load_email)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("lookup_crm",      self._lookup_crm)
        graph.add_node("draft_reply",     self._draft_reply)
        graph.add_node("send_reply",      self._send_reply)
        graph.add_node("escalate",        self._escalate)
        graph.add_node("create_ticket",   self._create_ticket)
        graph.add_node("enrich_lead",     self._enrich_lead)
        graph.add_node("archive",         self._archive)
        graph.add_node("queue_for_human", self._queue_for_human)
        graph.add_node("log_outcome",     self._log_outcome)

        # Entry point
        graph.set_entry_point("load_email")

        # Fixed edges
        graph.add_edge("load_email", "classify_intent")
        graph.add_edge("classify_intent", "lookup_crm")

        # Conditional routing after CRM lookup
        graph.add_conditional_edges(
            "lookup_crm",
            self._route_decision,
            {
                "support":   "draft_reply",
                "sales":     "enrich_lead",
                "complaint": "escalate",
                "urgent":    "escalate",
                "billing":   "draft_reply",
                "spam":      "archive",
                "other":     "queue_for_human",
            }
        )

        # Support path
        graph.add_edge("draft_reply", "send_reply")
        graph.add_edge("send_reply", "create_ticket")
        graph.add_edge("create_ticket", "log_outcome")

        # Sales path
        graph.add_edge("enrich_lead", "draft_reply")

        # Complaint/urgent path
        graph.add_edge("escalate", "create_ticket")

        # Terminal nodes
        graph.add_edge("archive", "log_outcome")
        graph.add_edge("queue_for_human", "log_outcome")
        graph.add_edge("log_outcome", END)

        return graph.compile()

    @log_step("load_email")
    def _load_email(self, state: EmailState) -> EmailState:
        """Normalise email fields and add defaults."""
        return {
            **state,
            "is_known_customer": False,
            "reply_sent": False,
            "escalated": False,
            "archived": False,
        }

    @log_step("classify_intent")
    @retry_node(max_attempts=3, delay_s=1.0)
    def _classify_intent(self, state: EmailState) -> EmailState:
        """LLM-based email classification with structured output."""
        prompt = CLASSIFICATION_PROMPT.format(
            sender=state.get("sender", "unknown"),
            subject=state.get("subject", "(no subject)"),
            body_preview=state.get("body_preview", "")[:500],
        )
        result = self.structured_llm_call(prompt)

        category = result.get("category", "other")
        if category not in ["support", "sales", "complaint", "billing",
                              "urgent", "spam", "other"]:
            category = "other"

        return {
            **state,
            "category": category,
            "priority": result.get("priority", "normal"),
            "confidence": float(result.get("confidence", 0.5)),
            "classification_reasoning": result.get("reasoning", ""),
        }

    @log_step("lookup_crm")
    def _lookup_crm(self, state: EmailState) -> EmailState:
        """Check CRM for existing relationship with sender."""
        # In production: query CRM API (Salesforce, HubSpot, etc.)
        # Mock: check if domain is known
        sender = state.get("sender", "")
        known_domains = ["acmecorp.com", "bigclient.io", "enterprise.co"]
        is_known = any(d in sender for d in known_domains)

        crm_contact = None
        if is_known:
            crm_contact = {
                "name": "ACME Corp",
                "deal_value": 50000,
                "account_owner": "sales@company.com",
                "account_stage": "customer",
            }

        return {
            **state,
            "is_known_customer": is_known,
            "crm_contact": crm_contact,
            "account_value": crm_contact["deal_value"] if crm_contact else None,
        }

    def _route_decision(self, state: EmailState) -> str:
        """Conditional edge: determine routing path from category."""
        category = state.get("category", "other")
        # High-value customer complaints always escalate first
        if category == "support" and state.get("account_value", 0) > 100000:
            return "complaint"
        return category

    @log_step("draft_reply")
    @retry_node(max_attempts=2)
    def _draft_reply(self, state: EmailState) -> EmailState:
        """Generate a personalised acknowledgement reply."""
        category = state.get("category", "support")
        template = REPLY_TEMPLATES.get(category, REPLY_TEMPLATES["support"])

        # Fill template variables
        reply = template.format(
            team={"support": "Technical Support", "billing": "Finance"}.get(category, "team"),
            ticket_id=state.get("ticket_id", "PENDING"),
            sla={"critical": "1 hour", "high": "4 hours", "normal": "24 hours", "low": "72 hours"}
                 .get(state.get("priority", "normal"), "24 hours"),
            assigned_owner=state.get("crm_contact", {}).get("account_owner", "our team") if state.get("crm_contact") else "our team"
        )

        return {**state, "draft_reply": reply}

    @log_step("send_reply")
    def _send_reply(self, state: EmailState) -> EmailState:
        """Send reply via SMTP. In production connects to Gmail/SMTP tools."""
        if not state.get("draft_reply"):
            return state
        # Production: from tools.email_tools import send_email; send_email(...)
        log.info(f"Reply sent to {state.get('sender')} | Priority: {state.get('priority')}")
        return {**state, "reply_sent": True}

    @log_step("escalate")
    def _escalate(self, state: EmailState) -> EmailState:
        """Send urgent Slack DM to on-call manager."""
        # Production: from tools.slack_tools import send_dm; send_dm(...)
        log.warning(f"ESCALATED: {state.get('subject')} from {state.get('sender')}")
        return {**state, "escalated": True}

    @log_step("create_ticket")
    def _create_ticket(self, state: EmailState) -> EmailState:
        """Create support ticket in ticketing system."""
        import hashlib
        ticket_id = f"TKT-{hashlib.md5(state.get('email_id', '').encode()).hexdigest()[:6].upper()}"
        log.info(f"Ticket created: {ticket_id} | Category: {state.get('category')}")
        return {**state, "ticket_id": ticket_id}

    @log_step("enrich_lead")
    def _enrich_lead(self, state: EmailState) -> EmailState:
        """Enrich lead data from email domain + external APIs."""
        # Production: from tools.crm_tools import enrich_contact; enrich_contact(...)
        log.info(f"Lead enriched: {state.get('sender')}")
        return {**state, "routed_to_team": "sales"}

    @log_step("archive")
    def _archive(self, state: EmailState) -> EmailState:
        log.info(f"Archived spam: {state.get('subject')}")
        return {**state, "archived": True}

    @log_step("queue_for_human")
    def _queue_for_human(self, state: EmailState) -> EmailState:
        log.info(f"Queued for human review: {state.get('email_id')}")
        return {**state, "routed_to_team": "general"}

    @log_step("log_outcome")
    def _log_outcome(self, state: EmailState) -> EmailState:
        """Write final triage record to database."""
        # Production: from tools.db_tools import log_triage; log_triage(state)
        log.info(
            f"Email {state.get('email_id')} | "
            f"Category: {state.get('category')} | "
            f"Priority: {state.get('priority')} | "
            f"Reply sent: {state.get('reply_sent')} | "
            f"Escalated: {state.get('escalated')}"
        )
        return state


def demo():
    """Run the agent on sample emails and print results."""
    agent = EmailTriageAgent(verbose=True)

    sample_emails = [
        {
            "email_id": "msg_001",
            "sender": "cto@bigclient.io",
            "subject": "URGENT: API integration down — production blocked",
            "body_preview": "Our entire production pipeline is blocked. Your API has been returning 503s for the last 2 hours. We have a client demo in 3 hours. This is critical.",
            "received_at": datetime.utcnow().isoformat(),
        },
        {
            "email_id": "msg_002",
            "sender": "procurement@newlead.com",
            "subject": "Interested in your analytics platform — pricing query",
            "body_preview": "Hi, I'm the procurement manager at NewLead Co. We're evaluating analytics platforms for our team of 200. Could you send pricing information and arrange a demo?",
            "received_at": datetime.utcnow().isoformat(),
        },
        {
            "email_id": "msg_003",
            "sender": "noreply@newsletter.io",
            "subject": "Your weekly industry digest is ready!",
            "body_preview": "This week in tech: AI developments, market trends...",
            "received_at": datetime.utcnow().isoformat(),
        },
    ]

    for email in sample_emails:
        print(f"\n{'='*60}")
        print(f"Processing: {email['subject'][:50]}")
        result = agent.run(email)
        print(f"Category:   {result.get('category')} ({result.get('priority')})")
        print(f"Confidence: {result.get('confidence', 0)*100:.0f}%")
        print(f"Reply sent: {result.get('reply_sent')} | Escalated: {result.get('escalated')}")
        print(f"Steps:      {result.get('processing_steps')}")
        if result.get("errors"):
            print(f"Errors:     {result.get('errors')}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    demo()
