import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from app.schemas import SavedTripDetail, TripRegenerationRequest, TripRequest, TripResponse


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_FILE)


class LLMConfigError(Exception):
    pass


class LLMUpstreamError(Exception):
    pass


class LLMOutputError(Exception):
    pass


@dataclass
class RegenerationContext:
    original_instruction: str
    expanded_instruction: str
    categories: list[str]


REGENERATION_RULES: dict[str, dict[str, list[str] | str]] = {
    "cheaper": {
        "keywords": [
            "cheap",
            "cheaper",
            "less expensive",
            "budget",
            "lower cost",
            "save money",
            "affordable",
        ],
        "rules": [
            "Avoid paid attractions when a good free alternative exists.",
            "Avoid rooftop restaurants and rooftop bars.",
            "Avoid hammams, cooking classes, premium cruises, and other premium add-ons.",
            "Avoid expensive ticketed landmarks and luxury experiences.",
            "Prefer ferries, markets, free walks, local neighborhoods, parks, beaches, street food, and affordable cafes.",
        ],
    },
    "less_touristy": {
        "keywords": [
            "less touristy",
            "less crowded",
            "quieter",
            "more local",
            "local vibe",
            "hidden gems",
            "off the beaten path",
        ],
        "rules": [
            "Avoid famous landmarks and crowded must-see attractions.",
            "Avoid places usually found in first-time tourist itineraries.",
            "Prefer local neighborhoods, smaller food places, quiet promenades, residential areas, hidden gems, and local markets.",
        ],
    },
    "more_relaxed": {
        "keywords": [
            "more relaxed",
            "slower",
            "less packed",
            "lighter",
            "easy pace",
            "not too busy",
            "rest",
        ],
        "rules": [
            "Reduce activities per day.",
            "Reduce walking distance and avoid back-and-forth routing.",
            "Add breaks and rest time.",
            "Avoid overpacked schedules and keep each day light and realistic.",
        ],
    },
    "less_time_on_road": {
        "keywords": [
            "less time on the road",
            "less travel time",
            "reduce transfers",
            "less transit",
            "less transportation",
            "closer together",
            "geographically compact",
        ],
        "rules": [
            "Keep the itinerary geographically compact.",
            "Avoid distant day trips, mountains, remote beaches, far villages, and airport-area detours unless truly necessary.",
            "Avoid multiple transport changes.",
            "Prefer nearby areas, same-zone planning, and shorter drives or transfers.",
        ],
    },
    "more_local_food": {
        "keywords": [
            "more local food",
            "local food",
            "street food",
            "regional food",
            "food markets",
            "traditional food",
        ],
        "rules": [
            "Add local food markets, street food, and regional specialties.",
            "Prefer small local eateries over generic chain food unless the user explicitly asked for chains.",
            "Make local food a visible part of the trip, not just a small note.",
        ],
    },
}


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise LLMConfigError(f"Missing required environment variable: {name}")
    return value


def _extract_json_text(content: str) -> str:
    cleaned_content = content.strip()

    if cleaned_content.startswith("```"):
        lines = cleaned_content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]

        cleaned_content = "\n".join(lines).strip()

    return cleaned_content


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _match_regeneration_categories(instruction: str) -> list[str]:
    normalized_instruction = _normalize_text(instruction)
    matched_categories: list[str] = []

    for category, config in REGENERATION_RULES.items():
        keywords = config["keywords"]
        if any(keyword in normalized_instruction for keyword in keywords):
            matched_categories.append(category)

    return matched_categories


def _expand_regeneration_instruction(instruction: str) -> RegenerationContext:
    cleaned_instruction = instruction.strip()
    categories = _match_regeneration_categories(cleaned_instruction)

    if not categories:
        return RegenerationContext(
            original_instruction=cleaned_instruction,
            expanded_instruction=cleaned_instruction,
            categories=[],
        )

    expanded_lines = [f"User request: {cleaned_instruction}", "", "Expanded strict rules:"]

    for category in categories:
        expanded_lines.append(f"- Category: {category.replace('_', ' ')}")
        for rule in REGENERATION_RULES[category]["rules"]:
            expanded_lines.append(f"  - {rule}")

    expanded_lines.append("- The requested change must be obvious in the summary, daily plans, and notes.")

    return RegenerationContext(
        original_instruction=cleaned_instruction,
        expanded_instruction="\n".join(expanded_lines),
        categories=categories,
    )


def _format_current_trip(current_trip: SavedTripDetail | None) -> str:
    if current_trip is None:
        return "No current itinerary was provided."

    day_lines = []
    for day in current_trip.days:
        day_lines.append(f"Day {day.day}: {day.plan}")

    day_text = "\n".join(day_lines) if day_lines else "No day plans were saved."

    return (
        f"Current title: {current_trip.title}\n"
        f"Current summary: {current_trip.summary}\n"
        f"Current notes: {current_trip.notes}\n"
        f"Current days:\n{day_text}"
    )


def _build_request_payload(
    prompt: str,
    model: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful travel planner. Always return valid JSON only, "
                    "with no extra explanation."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.7,
    }


def _build_prompt(
    trip: TripRequest,
    regeneration_instruction: str | None = None,
    current_trip: SavedTripDetail | None = None,
    retry_feedback: str | None = None,
) -> str:
    if regeneration_instruction and regeneration_instruction.strip():
        context = _expand_regeneration_instruction(regeneration_instruction)
        return _build_regeneration_prompt(trip, context, current_trip, retry_feedback)

    return _build_generation_prompt(trip)


def _build_generation_prompt(trip: TripRequest) -> str:
    additional_preferences = (
        trip.additional_preferences.strip()
        if trip.additional_preferences and trip.additional_preferences.strip()
        else ""
    )

    return f"""
Create a realistic travel itinerary as valid JSON.

Trip details:
- Destination: {trip.destination}
- Number of days: {trip.number_of_days}
- Budget: {trip.budget}
- Interests: {trip.interests}
- Travel style: {trip.travel_style}
- Additional preferences: {additional_preferences or "None"}

Return JSON only with this structure:
{{
  "title": "string",
  "summary": "string",
  "days": [
    {{
      "day": 1,
      "plan": "string"
    }}
  ],
  "notes": "string"
}}

Rules:
- Return JSON only. Do not add markdown, comments, or extra text.
- Make sure the "days" list contains exactly {trip.number_of_days} items.
- Write a short, specific trip title.
- Write a practical summary that matches the destination, budget, and travel style.
- Respect the stated budget and avoid suggesting activities that clearly conflict with it.
- Keep the pace consistent with the travel style.
- Avoid repeating the same attraction, neighborhood, or activity too often.
- Make the itinerary realistic for the number of days and avoid impossible travel timing.
- For each day, the "plan" string must be clearly organized with these sections in order:
  Morning: ...
  Afternoon: ...
  Evening: ...
- Mention a balanced mix of food, sightseeing, rest, and transport when appropriate.
- Keep notes concise and helpful. Include practical tips, reservations, or packing advice only when useful.
- If additional preferences are provided, treat them as user-specific wishes and reflect them where possible.
""".strip()


def _build_regeneration_prompt(
    trip: TripRequest,
    context: RegenerationContext,
    current_trip: SavedTripDetail | None = None,
    retry_feedback: str | None = None,
) -> str:
    additional_preferences = (
        trip.additional_preferences.strip()
        if trip.additional_preferences and trip.additional_preferences.strip()
        else ""
    )
    retry_block = ""
    if retry_feedback:
        retry_block = f"""
The previous regenerated itinerary failed validation.
Why it failed:
{retry_feedback}

You must correct those problems now. Do not repeat the same mistake.
""".strip()

    return f"""
You are a travel planning assistant.

Your task is to REGENERATE an existing trip plan based on a user instruction.

IMPORTANT RULES:
- The regeneration instruction is the HIGHEST PRIORITY.
- The requested change must be OBVIOUS in the title, summary, daily plans, and notes.
- If the user instruction conflicts with generic tourist planning, the user instruction wins.
- Replace weak matches with strong matches. Do not make only tiny edits.
- Keep the same destination and the same number of days.
- Return JSON only.

Original trip request:
- Destination: {trip.destination}
- Number of days: {trip.number_of_days}
- Budget: {trip.budget}
- Interests: {trip.interests}
- Travel style: {trip.travel_style}
- Additional preferences: {additional_preferences or "None"}

Current itinerary to revise:
{_format_current_trip(current_trip)}

User regeneration instruction:
{context.original_instruction}

Strengthened instruction:
{context.expanded_instruction}

{retry_block}

Return JSON only with this structure:
{{
  "title": "string",
  "summary": "string",
  "days": [
    {{
      "day": 1,
      "plan": "string"
    }}
  ],
  "notes": "string"
}}

Strict output rules:
- Return JSON only. Do not add markdown, comments, or extra text.
- Make sure the "days" list contains exactly {trip.number_of_days} items.
- Write a short, specific trip title.
- Write a practical summary that clearly reflects the requested change.
- For each day, the "plan" string must be clearly organized with these sections in order:
  Morning: ...
  Afternoon: ...
  Evening: ...
- Keep the itinerary realistic and internally consistent.
- In notes, briefly explain how the itinerary was changed to follow the instruction.
""".strip()


def _request_llm_content(
    prompt: str,
) -> str:
    api_key = _get_required_env("OPENAI_API_KEY")
    base_url = _get_required_env("OPENAI_BASE_URL")
    model = _get_required_env("OPENAI_MODEL")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=_build_request_payload(prompt, model),
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMUpstreamError("The LLM request timed out.") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        raise LLMUpstreamError(
            f"The LLM API returned an error status: {status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMUpstreamError(f"Failed to call the LLM API: {exc}") from exc

    try:
        response_data: dict[str, Any] = response.json()
    except ValueError as exc:
        raise LLMUpstreamError("The LLM API returned a non-JSON response.") from exc

    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMUpstreamError("The LLM API response did not include any choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise LLMUpstreamError("The LLM API returned an invalid choice format.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise LLMUpstreamError("The LLM API response did not include a valid message.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMUpstreamError("The LLM API response did not include text content.")

    return content


def _parse_trip_response(content: str) -> TripResponse:
    json_text = _extract_json_text(content)

    if not json_text:
        raise LLMOutputError("The LLM returned an empty response.")

    try:
        trip_plan_data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LLMOutputError("The LLM returned invalid JSON.") from exc

    if not isinstance(trip_plan_data, dict):
        raise LLMOutputError("The LLM returned JSON, but it was not a JSON object.")

    try:
        return TripResponse.model_validate(trip_plan_data)
    except Exception as exc:
        raise LLMOutputError(
            "The LLM returned JSON, but it did not match the expected trip format."
        ) from exc


def _collect_trip_text(trip_response: TripResponse) -> str:
    parts = [trip_response.title, trip_response.summary, trip_response.notes]
    parts.extend(day.plan for day in trip_response.days)
    return _normalize_text(" ".join(parts))


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _validate_cheaper(trip_response: TripResponse) -> list[str]:
    text = _collect_trip_text(trip_response)
    expensive_terms = [
        "rooftop",
        "hammam",
        "cooking class",
        "luxury",
        "premium",
        "palace",
        "expensive cruise",
        "high-end",
        "fine dining",
        "private yacht",
    ]

    problems = [term for term in expensive_terms if term in text]
    if problems:
        return [f"still includes expensive-sounding items: {', '.join(problems)}"]
    return []


def _validate_less_touristy(trip_response: TripResponse) -> list[str]:
    text = _collect_trip_text(trip_response)
    tourist_terms = [
        "hagia sophia",
        "blue mosque",
        "topkapi",
        "basilica cistern",
        "eiffel tower",
        "louvre",
        "colosseum",
        "times square",
        "burj khalifa",
    ]

    hit_count = _count_keyword_hits(text, tourist_terms)
    if hit_count >= 2:
        return ["still includes too many classic tourist landmarks"]
    return []


def _validate_less_time_on_road(trip_response: TripResponse) -> list[str]:
    text = _collect_trip_text(trip_response)
    travel_terms = [
        "airport transfer",
        "day trip",
        "mountains",
        "long drive",
        "remote village",
        "far beach",
        "monastery",
        "ferry ride to another town",
        "long transfer",
    ]

    problems = [term for term in travel_terms if term in text]
    if problems:
        return [f"still suggests long travel or distant detours: {', '.join(problems)}"]
    return []


def _validate_more_relaxed(trip_response: TripResponse) -> list[str]:
    overload_markers = [
        "then",
        "after that",
        "next",
        "continue to",
        "head to",
        "stop by",
        "visit",
        "explore",
    ]
    problems: list[str] = []

    for day in trip_response.days:
        plan_text = _normalize_text(day.plan)
        marker_count = sum(plan_text.count(marker) for marker in overload_markers)
        if marker_count >= 7 or "packed" in plan_text or "full-day" in plan_text:
            problems.append(f"day {day.day} still looks too busy")

    return problems


def _validate_more_local_food(trip_response: TripResponse) -> list[str]:
    text = _collect_trip_text(trip_response)
    local_food_terms = [
        "market",
        "street food",
        "local cafe",
        "family-run",
        "regional specialty",
        "traditional",
    ]
    generic_terms = ["chain restaurant", "international chain", "food court"]

    has_local_food = any(term in text for term in local_food_terms)
    generic_hits = [term for term in generic_terms if term in text]

    problems: list[str] = []
    if not has_local_food:
        problems.append("does not make local food visible enough")
    if generic_hits:
        problems.append(
            f"still relies on generic food choices: {', '.join(generic_hits)}"
        )

    return problems


def _validate_regenerated_trip(
    trip_response: TripResponse,
    context: RegenerationContext,
) -> list[str]:
    validation_problems: list[str] = []

    for category in context.categories:
        if category == "cheaper":
            validation_problems.extend(_validate_cheaper(trip_response))
        elif category == "less_touristy":
            validation_problems.extend(_validate_less_touristy(trip_response))
        elif category == "less_time_on_road":
            validation_problems.extend(_validate_less_time_on_road(trip_response))
        elif category == "more_relaxed":
            validation_problems.extend(_validate_more_relaxed(trip_response))
        elif category == "more_local_food":
            validation_problems.extend(_validate_more_local_food(trip_response))

    return validation_problems


def generate_trip_plan(
    trip: TripRequest,
    regeneration: TripRegenerationRequest | None = None,
    current_trip: SavedTripDetail | None = None,
) -> TripResponse:
    regeneration_instruction = None

    if regeneration is not None:
        regeneration_instruction = regeneration.regeneration_instruction

    prompt = _build_prompt(trip, regeneration_instruction, current_trip=current_trip)
    content = _request_llm_content(prompt)
    trip_response = _parse_trip_response(content)

    if not regeneration_instruction or not regeneration_instruction.strip():
        return trip_response

    context = _expand_regeneration_instruction(regeneration_instruction)
    validation_problems = _validate_regenerated_trip(trip_response, context)

    if not validation_problems:
        return trip_response

    retry_feedback = "\n".join(f"- {problem}" for problem in validation_problems)
    retry_prompt = _build_prompt(
        trip,
        regeneration_instruction,
        current_trip=current_trip,
        retry_feedback=retry_feedback,
    )
    retry_content = _request_llm_content(retry_prompt)
    retry_response = _parse_trip_response(retry_content)

    return retry_response
