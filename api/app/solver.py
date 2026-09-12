"""Deterministic, dependency-free training schedule solver.

This is deliberately a small executable T12 slice.  It consumes the typed
``training_schedule`` payload produced by T11 and searches the finite input
space with deterministic backtracking.  It never invents resources: missing
availability, malformed entities, and unknown required skills make the model
invalid or infeasible with an explanation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import PortfolioDefinitionIn, TrainingScheduleDefinitionIn


SOLVER_NAME = "lucid.training_backtracking.v1"
PORTFOLIO_SOLVER_NAME = "lucid.portfolio_enumeration.v1"


@dataclass(frozen=True)
class _Option:
    session: dict[str, Any]
    slot: dict[str, Any]
    room: dict[str, Any]
    instructor: dict[str, Any]


def _duplicate_keys(items: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in items:
        key = str(item.get("key") or "")
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["day"] == right["day"] and left["start_minute"] < right["end_minute"] and right["start_minute"] < left["end_minute"]


def _option_is_compatible(
    option: _Option, assignments: list[_Option], bindings: set[str]
) -> bool:
    for existing in assignments:
        if "no_overlap" in bindings and existing.slot["key"] == option.slot["key"] and existing.room["key"] == option.room["key"]:
            return False
        if "no_overlap" in bindings and existing.slot["key"] == option.slot["key"] and existing.instructor["key"] == option.instructor["key"]:
            return False
        if "no_overlap" in bindings and existing.instructor["key"] == option.instructor["key"] and _overlap(existing.slot, option.slot):
            return False
        if "no_overlap" in bindings and existing.room["key"] == option.room["key"] and _overlap(existing.slot, option.slot):
            return False
        if "cohort_no_overlap" in bindings and option.session.get("cohort") and option.session.get("cohort") == existing.session.get("cohort") and _overlap(existing.slot, option.slot):
            return False
    instructor = option.instructor
    same_day = sum(
        1
        for existing in assignments
        if existing.instructor["key"] == instructor["key"] and existing.slot["day"] == option.slot["day"]
    )
    return "daily_instructor_load" not in bindings or same_day < instructor["max_daily_sessions"]


def _score(
    assignments: list[_Option], objectives: list[tuple[str, int, float]]
) -> tuple[tuple[float, ...], float, dict[str, float]]:
    preferred_day_misses = sum(
        1
        for option in assignments
        if option.session.get("preferred_day") and option.session["preferred_day"] != option.slot["day"]
    )
    evening_sessions = sum(1 for option in assignments if option.slot["start_minute"] >= 18 * 60)
    metrics = {"preferred_day": float(preferred_day_misses), "evening_sessions": float(evening_sessions)}
    breakdown: dict[str, float] = {}
    score_parts: list[float] = []
    for binding, _priority, weight in objectives:
        value = metrics[binding] * weight
        breakdown[binding] = value
        score_parts.append(value)
    return tuple(score_parts), float(sum(score_parts)), breakdown


def _model_errors(data: dict[str, Any], bindings: set[str]) -> list[str]:
    errors: list[str] = []
    for collection in ("sessions", "time_slots", "rooms", "instructors"):
        items = data.get(collection) or []
        duplicates = _duplicate_keys(items)
        if duplicates:
            errors.append(f"duplicate {collection} key(s): {', '.join(duplicates)}")
    if not data.get("sessions"):
        errors.append("training schedule has no sessions")
    if not data.get("time_slots"):
        errors.append("training schedule has no time slots")
    if not data.get("rooms"):
        errors.append("training schedule has no rooms")
    if not data.get("instructors"):
        errors.append("training schedule has no instructors")
    for slot in data.get("time_slots") or []:
        if slot["end_minute"] <= slot["start_minute"]:
            errors.append(f"time slot {slot['key']} ends before it starts")
    if "room_availability" in bindings:
        for room in data.get("rooms") or []:
            if not room.get("available_slot_keys"):
                errors.append(f"room {room['key']} has no declared availability")
    if "instructor_availability" in bindings:
        for instructor in data.get("instructors") or []:
            if not instructor.get("available_slot_keys"):
                errors.append(f"instructor {instructor['key']} has no declared availability")
    return errors


def _build_options(
    model: TrainingScheduleDefinitionIn, bindings: set[str]
) -> tuple[list[tuple[str, list[_Option]]], dict[str, dict[str, int]]]:
    slots = {item.key: item.model_dump(mode="json") for item in model.time_slots}
    rooms = [item.model_dump(mode="json") for item in model.rooms]
    instructors = [item.model_dump(mode="json") for item in model.instructors]
    options_by_session: list[tuple[str, list[_Option]]] = []
    blockers: dict[str, dict[str, int]] = {}
    for session_model in sorted(model.sessions, key=lambda item: item.key):
        session = session_model.model_dump(mode="json")
        options: list[_Option] = []
        reasons = {"duration": 0, "slot_not_allowed": 0, "room_capacity": 0, "room_unavailable": 0, "instructor_unavailable": 0, "skill": 0, "evening_not_allowed": 0}
        if session["allowed_slot_keys"]:
            unknown_slot_count = sum(1 for key in session["allowed_slot_keys"] if key not in slots)
            reasons["slot_not_allowed"] += unknown_slot_count
            candidate_slots = [slots[key] for key in session["allowed_slot_keys"] if key in slots]
        else:
            candidate_slots = list(slots.values())
        for slot in sorted(candidate_slots, key=lambda item: item["key"]):
            if slot["end_minute"] - slot["start_minute"] < session["duration_minutes"]:
                reasons["duration"] += 1
                continue
            if slot["start_minute"] >= 18 * 60 and not model.allow_evening:
                reasons["evening_not_allowed"] += 1
                continue
            for room in sorted(rooms, key=lambda item: item["key"]):
                if "room_capacity" in bindings and room["capacity"] < session["attendees"]:
                    reasons["room_capacity"] += 1
                    continue
                if "room_availability" in bindings and slot["key"] not in room["available_slot_keys"]:
                    reasons["room_unavailable"] += 1
                    continue
                for instructor in sorted(instructors, key=lambda item: item["key"]):
                    if "instructor_availability" in bindings and slot["key"] not in instructor["available_slot_keys"]:
                        reasons["instructor_unavailable"] += 1
                        continue
                    required = session.get("required_skill")
                    if "instructor_skill" in bindings and required and required not in instructor["skills"]:
                        reasons["skill"] += 1
                        continue
                    options.append(_Option(session, slot, room, instructor))
        options_by_session.append((session["key"], options))
        blockers[session["key"]] = reasons
    return options_by_session, blockers


def solve_training_schedule(
    definition: dict[str, Any] | None,
    *,
    max_candidates: int = 3,
    max_search_nodes: int = 100_000,
) -> dict[str, Any]:
    if not definition or definition.get("family") != "training_schedule":
        return {"state": "model_invalid", "solver_name": SOLVER_NAME, "message": "formal model family must be training_schedule", "assignments": [], "objective_value": None, "explanation": {"issues": ["formal model family must be training_schedule"]}}
    raw = definition.get("training_schedule")
    try:
        model = TrainingScheduleDefinitionIn.model_validate(raw)
    except Exception as exc:
        return {"state": "model_invalid", "solver_name": SOLVER_NAME, "message": "training schedule definition is invalid", "assignments": [], "objective_value": None, "explanation": {"issues": [str(exc)]}}

    constraint_aliases = {
        "room_capacity": ("room_capacity", "capacity"),
        "room_availability": ("room_availability", "room availability", "room available"),
        "instructor_availability": ("instructor_availability", "instructor availability", "instructor available"),
        "instructor_skill": ("instructor_skill", "instructor skill", "required skill", "skill"),
        "no_overlap": ("no_overlap", "no overlap", "overlap"),
        "cohort_no_overlap": ("cohort_no_overlap", "cohort overlap", "same cohort"),
        "daily_instructor_load": ("daily_instructor_load", "daily instructor load", "daily load", "max daily"),
    }
    bindings: set[str] = set()
    unsupported_constraints: list[str] = []
    for item in definition.get("constraints") or []:
        if not item.get("enabled", True):
            continue
        binding = item.get("binding")
        haystack = f"{item.get('key', '')} {item.get('expression', '')}".lower()
        matched = binding if binding in constraint_aliases else next((name for name, aliases in constraint_aliases.items() if any(alias in haystack for alias in aliases)), None)
        if matched is None:
            unsupported_constraints.append(str(item.get("key") or item.get("expression") or "<unnamed>"))
        else:
            bindings.add(matched)
    if unsupported_constraints or not bindings:
        return {"state": "model_invalid", "solver_name": SOLVER_NAME, "message": "training schedule contains unsupported or missing executable constraints", "assignments": [], "objective_value": None, "explanation": {"issues": [f"unsupported constraint: {item}" for item in unsupported_constraints] or ["at least one executable constraint is required"], "supported_constraints": sorted(constraint_aliases)}}

    objective_aliases = {
        "preferred_day": ("preferred_day", "preferred day", "preferred"),
        "evening_sessions": ("evening_sessions", "evening session", "late session", "late"),
    }
    objectives: list[tuple[str, int, float]] = []
    unsupported_objectives: list[str] = []
    for item in definition.get("objectives") or []:
        binding = item.get("binding")
        haystack = f"{item.get('key', '')} {item.get('expression', '')}".lower()
        matched = binding if binding in objective_aliases else next((name for name, aliases in objective_aliases.items() if any(alias in haystack for alias in aliases)), None)
        if item.get("direction") != "minimize" or matched is None:
            unsupported_objectives.append(str(item.get("key") or item.get("expression") or "<unnamed>"))
        else:
            objectives.append((matched, int(item.get("priority") or 1), float(item.get("weight") or 1.0)))
    if not objectives or unsupported_objectives:
        return {"state": "model_invalid", "solver_name": SOLVER_NAME, "message": "training schedule objective is unsupported or missing", "assignments": [], "objective_value": None, "explanation": {"issues": [f"unsupported objective: {item}" for item in unsupported_objectives] or ["at least one executable minimizing objective is required"], "supported_objectives": sorted(objective_aliases)}}
    objectives.sort(key=lambda item: (item[1], item[0]))

    errors = _model_errors(model.model_dump(mode="json"), bindings)
    if errors:
        return {"state": "model_invalid", "solver_name": SOLVER_NAME, "message": "training schedule definition is incomplete", "assignments": [], "objective_value": None, "explanation": {"issues": errors}}
    options_by_session, blockers = _build_options(model, bindings)
    empty = [key for key, options in options_by_session if not options]
    if empty:
        return {"state": "infeasible", "solver_name": SOLVER_NAME, "message": "one or more sessions have no individually feasible assignment", "assignments": [], "objective_value": None, "explanation": {"empty_sessions": empty, "blockers": blockers}}

    order = sorted(range(len(options_by_session)), key=lambda index: (len(options_by_session[index][1]), options_by_session[index][0]))
    solutions: list[tuple[tuple[float, ...], float, list[_Option], dict[str, float]]] = []
    nodes = 0
    budget_exhausted = False

    def search(position: int, chosen: list[_Option]) -> None:
        nonlocal nodes, budget_exhausted
        if nodes >= max_search_nodes:
            budget_exhausted = True
            return
        nodes += 1
        if position == len(order):
            score, value, breakdown = _score(chosen, objectives)
            solutions.append((score, value, list(chosen), breakdown))
            solutions.sort(key=lambda item: (item[0], tuple(option.session["key"] for option in item[2])))
            del solutions[max_candidates:]
            return
        session_index = order[position]
        for option in options_by_session[session_index][1]:
            if _option_is_compatible(option, chosen, bindings):
                chosen.append(option)
                search(position + 1, chosen)
                chosen.pop()
                if budget_exhausted:
                    return

    search(0, [])
    if budget_exhausted and not solutions:
        return {"state": "unknown", "solver_name": SOLVER_NAME, "message": "search budget exhausted before a complete assignment was found", "assignments": [], "objective_value": None, "explanation": {"search_nodes": nodes, "max_search_nodes": max_search_nodes, "blockers": blockers}}
    if not solutions:
        return {"state": "infeasible", "solver_name": SOLVER_NAME, "message": "no assignment satisfies the declared training constraints", "assignments": [], "objective_value": None, "explanation": {"blockers": blockers, "searched_sessions": len(model.sessions), "search_nodes": nodes}}

    def render_assignments(options: list[_Option]) -> list[dict[str, Any]]:
        return [{"session_key": option.session["key"], "session_name": option.session["name"], "day": option.slot["day"], "slot_key": option.slot["key"], "start_minute": option.slot["start_minute"], "end_minute": option.slot["end_minute"], "room_key": option.room["key"], "room_name": option.room["name"], "instructor_key": option.instructor["key"], "instructor_name": option.instructor["name"], "attendees": option.session["attendees"]} for option in sorted(options, key=lambda item: item.session["key"])]

    candidates = [{"assignments": render_assignments(options), "objective_value": value, "objective_breakdown": breakdown} for _score_key, value, options, breakdown in solutions]
    best = candidates[0]
    return {"state": "unknown" if budget_exhausted else "optimal", "solver_name": SOLVER_NAME, "message": "deterministic search found the best schedule within the search budget" if budget_exhausted else "deterministic exhaustive search found an optimal schedule", "assignments": best["assignments"], "objective_value": best["objective_value"], "objective_breakdown": best["objective_breakdown"], "candidate_count": len(candidates), "candidates": candidates, "explanation": {"declared_constraints": sorted(bindings), "blockers": blockers, "search_nodes": nodes, "max_search_nodes": max_search_nodes, "search_budget_exhausted": budget_exhausted}}


def solve_portfolio(
    definition: dict[str, Any] | None, *, max_candidates: int = 5
) -> dict[str, Any]:
    """Enumerate a finite portfolio model deterministically.

    The solver only accepts the typed ``portfolio`` payload. It never fills in
    missing costs, values, conflicts, or budget assumptions.
    """
    if not definition or definition.get("family") != "portfolio":
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "formal model family must be portfolio",
            "candidates": [],
            "explanation": {"issues": ["formal model family must be portfolio"]},
        }
    try:
        model = PortfolioDefinitionIn.model_validate(definition.get("portfolio"))
    except Exception as exc:
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "portfolio definition is invalid",
            "candidates": [],
            "explanation": {"issues": [str(exc)]},
        }
    objectives = definition.get("objectives") or []
    if not objectives:
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "portfolio formal model has no objective",
            "candidates": [],
            "explanation": {"issues": ["at least one objective is required"]},
        }
    objective_matches = [
        item for item in objectives
        if item.get("direction") == "maximize"
        and (
            item.get("binding") == "portfolio_value"
            or any(token in f"{item.get('key', '')} {item.get('expression', '')}".lower() for token in ("value", "benefit"))
        )
    ]
    if not objective_matches:
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "portfolio objective must maximize item value",
            "candidates": [],
            "explanation": {"issues": ["supported objective: maximize total item value"]},
        }
    constraint_aliases = {
        "portfolio_budget": ("portfolio_budget", "budget", "cost <= budget", "sum(cost)"),
        "portfolio_required": ("portfolio_required", "required item", "required"),
        "portfolio_conflict": ("portfolio_conflict", "conflict", "mutually exclusive"),
    }
    unsupported_constraints: list[str] = []
    portfolio_bindings: set[str] = set()
    for item in definition.get("constraints") or []:
        if not item.get("enabled", True):
            continue
        binding = item.get("binding")
        haystack = f"{item.get('key', '')} {item.get('expression', '')}".lower()
        matched = binding if binding in constraint_aliases else next(
            (name for name, aliases in constraint_aliases.items() if any(alias in haystack for alias in aliases)),
            None,
        )
        if matched is None:
            unsupported_constraints.append(str(item.get("key") or item.get("expression") or "<unnamed>"))
        else:
            portfolio_bindings.add(matched)
    if "portfolio_budget" not in portfolio_bindings or unsupported_constraints:
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "portfolio contains unsupported or missing executable constraints",
            "candidates": [],
            "explanation": {
                "issues": [f"unsupported constraint: {item}" for item in unsupported_constraints]
                or ["a budget constraint is required"],
                "supported_constraints": sorted(constraint_aliases),
            },
        }
    items = sorted(model.items, key=lambda item: item.key)
    keys = [item.key for item in items]
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "portfolio contains duplicate item keys",
            "candidates": [],
            "explanation": {"issues": [f"duplicate item key: {key}" for key in duplicate_keys]},
        }
    known = set(keys)
    unknown_conflicts = sorted(
        {
            conflict
            for item in items
            for conflict in item.conflict_keys
            if conflict not in known
        }
    )
    if unknown_conflicts:
        return {
            "state": "model_invalid",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "portfolio conflict references an unknown item",
            "candidates": [],
            "explanation": {"issues": [f"unknown conflict key: {key}" for key in unknown_conflicts]},
        }
    required = {item.key for item in items if item.required}
    for item in items:
        if item.key in item.conflict_keys:
            return {
                "state": "model_invalid",
                "solver_name": PORTFOLIO_SOLVER_NAME,
                "message": "portfolio item conflicts with itself",
                "candidates": [],
                "explanation": {"issues": [f"self conflict: {item.key}" ]},
            }
    candidates: list[dict[str, Any]] = []
    n = len(items)
    for mask in range(1 << n):
        selected = [items[index] for index in range(n) if mask & (1 << index)]
        selected_keys = {item.key for item in selected}
        if not required.issubset(selected_keys):
            continue
        if sum(item.cost for item in selected) > model.budget + 1e-9:
            continue
        if any(conflict in selected_keys for item in selected for conflict in item.conflict_keys):
            continue
        cost = sum(item.cost for item in selected)
        value = sum(item.value for item in selected)
        candidates.append(
            {
                "selected_keys": sorted(selected_keys),
                "selected_items": [item.model_dump(mode="json") for item in selected],
                "cost": cost,
                "value": value,
                "remaining_budget": model.budget - cost,
            }
        )
    candidates.sort(
        key=lambda candidate: (
            -candidate["value"],
            candidate["cost"],
            tuple(candidate["selected_keys"]),
        )
    )
    candidates = candidates[:max_candidates]
    if not candidates:
        return {
            "state": "infeasible",
            "solver_name": PORTFOLIO_SOLVER_NAME,
            "message": "no portfolio satisfies required items, budget, and conflict constraints",
            "candidates": [],
            "explanation": {
                "budget": model.budget,
                "required_keys": sorted(required),
                "items": [item.key for item in items],
            },
        }
    return {
        "state": "optimal",
        "solver_name": PORTFOLIO_SOLVER_NAME,
        "message": "deterministic portfolio enumeration found ranked feasible selections",
        "candidates": candidates,
        "objective_value": candidates[0]["value"],
        "explanation": {
            "objective": "maximize total item value",
            "hard_constraints": ["budget", "required items", "pairwise conflicts"],
            "enumerated_subsets": 1 << n,
        },
    }
