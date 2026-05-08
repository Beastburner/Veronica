from __future__ import annotations

"""
planner.py — Multi-step goal decomposer using LLM for Veronica AI assistant.

No new DB tables — writes into the existing `tasks` table via
`from app.storage import perform_create_task`.

Uses `call_json()` from app.llm_client to decompose a natural-language goal
into 4-7 concrete, actionable steps.
"""

from typing import Any

from app.llm_client import call_json
from app.storage import perform_create_task


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_plan_prompt(goal: str) -> str:
    """
    Build the LLM prompt for decomposing a goal into steps.

    Args:
        goal: The high-level goal the user wants to accomplish.

    Returns:
        A formatted prompt string ready for call_json().
    """
    return (
        f"Goal: {goal!r}\n\n"
        "Decompose this goal into 4–7 concrete, actionable steps. "
        "Each step must be a clear, independently executable task. "
        'Return ONLY valid JSON matching the schema: '
        '{"steps": [{"task": string, "description": string, '
        '"priority": "high"|"medium"|"low", "order": int}]}'
    )


# ---------------------------------------------------------------------------
# Schema hint for call_json
# ---------------------------------------------------------------------------

_PLAN_SCHEMA_HINT: str = (
    '{"steps": [{"task": string, "description": string, '
    '"priority": "high"|"medium"|"low", "order": int}]} '
    "Extract 4-7 concrete, actionable steps to accomplish the goal. "
    "Each step should be a clear task."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decompose_goal(
    goal: str,
    auto_create: bool = False,
) -> dict[str, Any]:
    """
    Decompose a high-level goal into actionable steps using the LLM.

    Args:
        goal:        Natural-language description of the goal.
        auto_create: If True, create each step as a task in the DB and
                     return the created task dicts under the "tasks" key.

    Returns:
        {
            "goal": str,
            "steps": [{"task", "description", "priority", "order"}, ...],
            "created": bool,
            "tasks": [...]   # only present when auto_create=True
        }
    """
    prompt = build_plan_prompt(goal)
    payload = call_json(prompt, schema_hint=_PLAN_SCHEMA_HINT, max_tokens=600)

    if payload is None or "steps" not in payload:
        return {
            "goal": goal,
            "steps": [],
            "created": False,
            "error": "LLM did not return a valid plan. Please try again.",
        }

    raw_steps: list[dict[str, Any]] = payload["steps"]

    # Normalise + sort by order field
    steps: list[dict[str, Any]] = []
    for i, step in enumerate(raw_steps):
        steps.append(
            {
                "task": str(step.get("task", "")),
                "description": str(step.get("description", "")),
                "priority": str(step.get("priority", "medium")),
                "order": int(step.get("order", i + 1)),
            }
        )
    steps.sort(key=lambda s: s["order"])

    result: dict[str, Any] = {
        "goal": goal,
        "steps": steps,
        "created": False,
    }

    if auto_create:
        created_tasks: list[dict[str, Any]] = []
        for step in steps:
            # Build a descriptive task string for storage
            task_text = step["task"]
            if step["description"]:
                task_text = f"{step['task']} — {step['description']}"
            task_result = perform_create_task(task_text)
            task_result["step_order"] = step["order"]
            task_result["priority"] = step["priority"]
            created_tasks.append(task_result)
        result["created"] = True
        result["tasks"] = created_tasks

    return result
