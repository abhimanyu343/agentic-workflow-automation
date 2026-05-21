"""
LangChain-based email triage agent.
Classifies emails, determines priority, drafts responses, routes to appropriate team.
"""
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
import json
from typing import Optional


TRIAGE_SYSTEM_PROMPT = """You are an intelligent email triage assistant for a business operations team.

Your job is to:
1. Classify incoming emails by category (support, sales, complaint, billing, partnership, spam)
2. Assign priority (urgent, high, normal, low) based on content and sender
3. Draft a professional acknowledgement reply
4. Suggest which team should handle it

Always respond in JSON format with keys: category, priority, team, draft_reply, reasoning
"""

@tool
def classify_sender_domain(email: str) -> str:
    """Look up information about the sender domain to assess legitimacy and company size."""
    domain = email.split("@")[-1] if "@" in email else email
    return f"Domain {domain}: verified business domain. Estimated company size: mid-market."

@tool
def check_crm(email: str) -> str:
    """Check CRM for existing relationship with this email address."""
    # In production: query actual CRM API
    return json.dumps({
        "found": True,
        "name": "Sample Contact",
        "company": "ACME Corp",
        "deal_value": 50000,
        "last_contact": "2026-04-15",
        "account_owner": "sales@company.com"
    })

@tool  
def draft_reply(context: str) -> str:
    """Generate a professional email reply based on context."""
    return f"Thank you for reaching out. Your inquiry has been received and will be handled by our team within 24 hours. Reference: {hash(context) % 100000}"

@tool
def route_to_team(team: str, email_id: str, priority: str) -> str:
    """Route email to the appropriate team in the ticketing system."""
    return f"Routed email {email_id} to {team} team with priority {priority}. Ticket created."


def build_triage_agent(model: str = "gpt-4o-mini"):
    llm = ChatOpenAI(model=model, temperature=0)
    tools = [classify_sender_domain, check_crm, draft_reply, route_to_team]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", TRIAGE_SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])
    
    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=5)


def triage_email(subject: str, body: str, sender: str, agent: Optional[AgentExecutor] = None) -> dict:
    """
    Triage a single email.
    
    Args:
        subject: Email subject line
        body: Email body text
        sender: Sender email address
        agent: Pre-built agent (builds new if None)
    
    Returns:
        dict with category, priority, team, draft_reply, reasoning
    """
    if agent is None:
        agent = build_triage_agent()
    
    prompt = f"""
    Triage this email:
    From: {sender}
    Subject: {subject}
    Body: {body[:500]}
    
    Use your tools to check the sender and CRM, then classify and route.
    """
    
    result = agent.invoke({"input": prompt})
    try:
        import re
        json_match = re.search(r'\{.*\}', result["output"], re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass
    return {"raw_output": result["output"]}
