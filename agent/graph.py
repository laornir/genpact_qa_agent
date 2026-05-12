"""
LangGraph graph assembly for the university QA agent.

``build_graph()`` wires all nodes and conditional edges into a compiled
LangGraph ``StateGraph``.  The compiled graph is invoked with
``await graph.ainvoke(initial_state, config=config)`` where ``config``
carries the injected dependencies (LLM, connector, few-shot examples, limits).

Graph flow::

    question_analyzer
        ├─ "generating"          → sql_generator
        ├─ "asking_clarification" → END
        └─ "error"               → END

    sql_generator → sql_validator
        ├─ "executing"           → sql_executor
        └─ "error"               → END

    sql_executor
        ├─ "formatting"          → answer_formatter → END
        ├─ "generating"          → sql_generator  (retry loop)
        └─ "error"               → END

Usage::

    from agent.graph import build_graph

    graph = build_graph()
    result = await graph.ainvoke(initial_state, config={
        "configurable": {
            "llm":                   llm,
            "connector":             connector,
            "few_shot_examples":     examples,
            "max_clarification_rounds": 3,
            "max_sql_retries":       2,
            "db_results_row_limit":  50,
        }
    })

Settings used (all injected via ``config["configurable"]`` at invoke time):
    llm, connector, few_shot_examples, max_clarification_rounds,
    max_sql_retries, db_results_row_limit
"""

from langgraph.graph import END, StateGraph

from agent.nodes.answer_formatter import answer_formatter
from agent.nodes.question_analyzer import question_analyzer
from agent.nodes.sql_executor import sql_executor
from agent.nodes.sql_generator import sql_generator
from agent.nodes.sql_validator import sql_validator
from agent.state import AgentState


def _route(state: AgentState) -> str:
    """Return the current status string to drive conditional edge routing."""
    return state["status"]


def build_graph():
    """
    Assemble and compile the university QA agent graph.

    Returns:
        A compiled LangGraph ``CompiledGraph`` ready for ``ainvoke``.
    """
    workflow: StateGraph = StateGraph(AgentState)

    workflow.add_node("question_analyzer", question_analyzer)
    workflow.add_node("sql_generator", sql_generator)
    workflow.add_node("sql_validator", sql_validator)
    workflow.add_node("sql_executor", sql_executor)
    workflow.add_node("answer_formatter", answer_formatter)

    workflow.set_entry_point("question_analyzer")

    workflow.add_conditional_edges(
        "question_analyzer",
        _route,
        {
            "generating": "sql_generator",
            "asking_clarification": END,
            "error": END,
        },
    )

    workflow.add_edge("sql_generator", "sql_validator")

    workflow.add_conditional_edges(
        "sql_validator",
        _route,
        {
            "executing": "sql_executor",
            "error": END,
        },
    )

    workflow.add_conditional_edges(
        "sql_executor",
        _route,
        {
            "formatting": "answer_formatter",
            "generating": "sql_generator",  # retry loop
            "error": END,
        },
    )

    workflow.add_edge("answer_formatter", END)

    return workflow.compile()
