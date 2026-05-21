"""
Abstract base class for all LangGraph-based agents.

Provides:
- Standard LLM factory (OpenAI / local Ollama)
- Shared tool registry
- Structured output parsing helpers
- Error handling + retry decorator
- Step logging (populates processing_steps in state)
- Async execution support

All agents extend this and implement `build_graph()`.
"""

import logging
import time
import functools
import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar, Callable
from datetime import datetime

log = logging.getLogger(__name__)
T = TypeVar("T")


def retry_node(max_attempts: int = 3, delay_s: float = 1.0, exceptions=(Exception,)):
    """
    Decorator for LangGraph node functions that adds retry logic.
    Appends error messages to state["errors"] and re-raises on final failure.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict, *args, **kwargs) -> dict:
            errors = list(state.get("errors", []))
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(state, *args, **kwargs)
                except exceptions as e:
                    msg = f"{fn.__name__} attempt {attempt}/{max_attempts}: {e}"
                    errors.append(msg)
                    log.warning(msg)
                    if attempt < max_attempts:
                        time.sleep(delay_s * attempt)
                    else:
                        log.error(f"{fn.__name__} failed after {max_attempts} attempts")
                        return {**state, "errors": errors}
            return state
        return wrapper
    return decorator


def log_step(step_name: str):
    """Decorator that appends step_name to state['processing_steps']."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict, *args, **kwargs) -> dict:
            t0 = time.time()
            result = fn(state, *args, **kwargs)
            elapsed = round((time.time() - t0) * 1000)
            steps = list(state.get("processing_steps", []))
            steps.append(f"{step_name} ({elapsed}ms)")
            return {**result, "processing_steps": steps}
        return wrapper
    return decorator


def parse_llm_json(text: str, schema: Optional[Dict] = None) -> Dict:
    """
    Parse JSON from LLM output, handling common failure modes:
    - JSON wrapped in ```json ... ``` fences
    - Trailing commas
    - Single quotes instead of double quotes
    - Extra text before/after the JSON block
    """
    if hasattr(text, "content"):
        text = text.content  # LangChain AIMessage

    # Try raw parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    text_clean = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object/array
    match = re.search(r"(\{.*\}|\[.*\])", text_clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fix trailing commas (common LLM mistake)
    text_fixed = re.sub(r",\s*([}\]])", r"", text_clean)
    try:
        return json.loads(text_fixed)
    except json.JSONDecodeError:
        pass

    log.warning(f"Failed to parse JSON from LLM output: {text[:200]}")
    return {}


class BaseAgent(ABC):
    """
    Abstract base for all LangGraph agents.

    Subclasses implement:
    - build_graph(): returns a compiled LangGraph StateGraph
    - run(input_state): entry point, sets up initial state and invokes graph
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        local: bool = False,
        verbose: bool = False,
    ):
        self.model_name = model
        self.temperature = temperature
        self.local = local
        self.verbose = verbose
        self._llm = None
        self._graph = None

    @property
    def llm(self):
        """Lazy-loaded LLM (OpenAI or local Ollama)."""
        if self._llm is None:
            if self.local:
                from langchain_community.llms import Ollama
                self._llm = Ollama(model="llama3", temperature=self.temperature)
            else:
                from langchain_openai import ChatOpenAI
                self._llm = ChatOpenAI(
                    model=self.model_name,
                    temperature=self.temperature,
                    response_format=None,
                )
        return self._llm

    @property
    def graph(self):
        """Lazy-build and cache the compiled LangGraph."""
        if self._graph is None:
            self._graph = self.build_graph()
        return self._graph

    @abstractmethod
    def build_graph(self):
        """Build and return a compiled langgraph.graph.StateGraph."""
        ...

    def run(self, input_state: Dict[str, Any], config: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Invoke the agent graph synchronously.

        Args:
            input_state: Initial state dict
            config: Optional LangGraph config (checkpointer, thread_id, etc.)

        Returns:
            Final state dict after all nodes have run
        """
        t0 = time.time()
        initial = {
            "processing_steps": [],
            "errors": [],
            **input_state
        }
        try:
            final_state = self.graph.invoke(initial, config=config)
        except Exception as e:
            log.error(f"Agent graph failed: {e}", exc_info=True)
            final_state = {**initial, "errors": [str(e)]}

        elapsed = round((time.time() - t0) * 1000)
        final_state["total_latency_ms"] = elapsed
        final_state["completed_at"] = datetime.utcnow().isoformat()

        if self.verbose:
            log.info(f"Agent completed in {elapsed}ms")
            log.info(f"Steps: {final_state.get('processing_steps', [])}")
            if final_state.get("errors"):
                log.warning(f"Errors: {final_state['errors']}")

        return final_state

    def structured_llm_call(self, prompt: str, output_schema: str = "") -> Dict:
        """
        Call LLM and parse structured JSON output.

        Args:
            prompt: Full prompt to send
            output_schema: Description of expected JSON format to append to prompt

        Returns:
            Parsed dict from LLM JSON response
        """
        full_prompt = prompt
        if output_schema:
            full_prompt += f"\n\nRespond ONLY with valid JSON matching this schema:\n{output_schema}"

        response = self.llm.invoke(full_prompt)
        return parse_llm_json(response)
