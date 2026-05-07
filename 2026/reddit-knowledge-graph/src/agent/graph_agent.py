"""
graph_agent.py
──────────────
LangGraph-based AI agent for the Reddit Knowledge Graph.

Architecture
────────────
Uses a ReAct (Reason + Act) pattern implemented with LangGraph:

    ┌─────────────┐      tool_calls      ┌──────────────┐
    │  LLM Node   │────────────────────► │  Tools Node  │
    │  (Claude)   │◄────────────────────  │  (Neo4j Q.)  │
    └─────────────┘    tool_results      └──────────────┘
          │
          │ (no more tool calls)
          ▼
        END

The agent loop:
1. User sends a question.
2. Claude decides which tool(s) to call.
3. Tools query Neo4j and return results.
4. Claude synthesises results into a final answer.
5. If Claude needs more data, it calls more tools (multi-hop).

Usage
─────
    from src.agent.graph_agent import build_agent
    agent = build_agent()
    response = agent.invoke({"messages": [("human", "Where is Neo4j discussed most?")]})
    print(response["messages"][-1].content)
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import ALL_TOOLS
from src.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# State definition
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """
    The state passed between nodes in the LangGraph graph.

    `messages` uses LangGraph's `add_messages` reducer, which appends new
    messages to the list rather than replacing it — enabling multi-turn
    conversations and multi-hop tool calls within a single invocation.
    """
    messages: Annotated[list[BaseMessage], add_messages]


# ─────────────────────────────────────────────────────────────────────────────
# Node definitions
# ─────────────────────────────────────────────────────────────────────────────

def build_llm() -> ChatAnthropic:
    """
    Build and return a Claude LLM instance bound to all agent tools.

    The model is configured with:
    - A system prompt describing the agent's role and available data.
    - Tool schemas from ALL_TOOLS so Claude knows how to call each one.
    """
    llm = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        temperature=0,         # Deterministic tool-calling
        max_tokens=4096,
    )
    return llm.bind_tools(ALL_TOOLS)


def llm_node(state: AgentState) -> AgentState:
    """
    The LLM node: invoke Claude with the current message history.

    Prepends the system prompt on the first call in each conversation turn.
    Returns the assistant's response (possibly with tool_calls).
    """
    messages = state["messages"]

    # Prepend system message if not already present
    from langchain_core.messages import SystemMessage
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    llm = build_llm()
    response = llm.invoke(messages)

    logger.debug(
        "LLM response: %s tool calls",
        len(response.tool_calls) if hasattr(response, "tool_calls") else 0,
    )

    return {"messages": [response]}


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────

def build_agent():
    """
    Build and compile the LangGraph ReAct agent.

    Graph topology:
        START → llm_node → (tool_node → llm_node)* → END

    The `tools_condition` edge routes back to tool_node if the LLM returned
    tool_calls, or to END if it returned a plain text response.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph that can be invoked with `.invoke()` or
        streamed with `.stream()`.
    """
    # ── Define the tool execution node ───────────────────────────────────────
    tool_node = ToolNode(tools=ALL_TOOLS)

    # ── Build the graph ───────────────────────────────────────────────────────
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)

    # Edges
    graph.add_edge(START, "llm")

    # Conditional: if LLM called tools → go to tool node; else → END
    graph.add_conditional_edges(
        "llm",
        tools_condition,
        {"tools": "tools", END: END},
    )

    # After tools run, always go back to LLM for synthesis
    graph.add_edge("tools", "llm")

    compiled = graph.compile()
    logger.info("LangGraph agent compiled with %d tools.", len(ALL_TOOLS))
    return compiled


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers
# ─────────────────────────────────────────────────────────────────────────────

def ask(question: str) -> str:
    """
    Ask the agent a single question and return the final text answer.

    This is a convenience wrapper for one-shot question answering.

    Parameters
    ----------
    question : str
        A natural-language question about the Reddit knowledge graph.

    Returns
    -------
    str
        The agent's final synthesised answer.
    """
    agent = build_agent()
    result = agent.invoke({"messages": [("human", question)]})

    # The last message is always the LLM's final response
    last_message = result["messages"][-1]
    if isinstance(last_message, AIMessage):
        return last_message.content
    return str(last_message)


def stream_ask(question: str):
    """
    Ask the agent a question and yield intermediate steps + final answer.

    Useful for streaming UIs or CLI display of tool calls in real time.

    Yields
    ------
    dict
        LangGraph event dicts with keys like 'llm', 'tools', etc.
    """
    agent = build_agent()
    for event in agent.stream({"messages": [("human", question)]}):
        yield event
