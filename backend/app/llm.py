import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from app.schemas import TripRegenerationRequest, TripRequest, TripResponse


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_FILE)


class LLMConfigError(Exception):
    pass


class LLMUpstreamError(Exception):
    pass


class LLMOutputError(Exception):
    pass


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


def _build_request_payload(
    trip: TripRequest,
    model: str,
    regeneration_instruction: str | None = None,
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
                "content": _build_prompt(trip, regeneration_instruction),
            },
        ],
        "temperature": 0.7,
    }


def _build_prompt(
    trip: TripRequest,
    regeneration_instruction: str | None = None,
) -> str:
    if regeneration_instruction and regeneration_instruction.strip():
        return _build_regeneration_prompt(trip, regeneration_instruction)

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
    regeneration_instruction: str,
) -> str:
    additional_preferences = (
        trip.additional_preferences.strip()
        if trip.additional_preferences and trip.additional_preferences.strip()
        else ""
    )
    regeneration_note = regeneration_instruction.strip()

    original_trip = f"""
Destination: {trip.destination}
Number of days: {trip.number_of_days}
Budget: {trip.budget}
Interests: {trip.interests}
Travel style: {trip.travel_style}
Additional preferences: {additional_preferences or "None"}
""".strip()

    return f"""
You are a travel planning assistant.

Your task is to MODIFY an existing trip plan based on a user instruction.

IMPORTANT RULES:
- The regeneration instruction is the HIGHEST PRIORITY
- You MUST strictly follow it
- The new plan MUST clearly reflect the requested change
- If the instruction conflicts with the original plan, IGNORE the original plan

Original trip:
{original_trip}

User regeneration instruction:
{regeneration_note}

STRICT REQUIREMENTS:
- If user asks to make it cheaper:
  - remove or replace paid attractions
  - avoid rooftop restaurants and rooftop bars
  - avoid hammams
  - avoid cooking classes
  - avoid premium cruises
  - avoid expensive tourist landmarks
  - prefer public ferries, local neighborhoods, markets, parks, mosques, waterfront walks, affordable cafes, and street food

- If user asks for less touristy:
  - avoid famous landmarks and expensive tourist landmarks
  - avoid crowded places
  - focus on local neighborhoods and hidden spots

- If user asks for more relaxed:
  - reduce number of activities per day
  - shorten walking distances
  - include breaks and rest time

- The new itinerary must visibly change to match the instruction.
- Do not keep expensive or tourist-heavy choices if the instruction asks to remove them.
- Keep the trip realistic for the same destination and number of days.

Output format:
- title
- summary
- days (day-by-day plan)
- notes

Additionally:
In the notes section, briefly explain how the plan was adjusted based on the instruction.

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
- Write a practical summary that clearly reflects the requested change.
- For each day, the "plan" string must be clearly organized with these sections in order:
  Morning: ...
  Afternoon: ...
  Evening: ...
""".strip()


def _request_llm_content(
    trip: TripRequest,
    regeneration_instruction: str | None = None,
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
                json=_build_request_payload(trip, model, regeneration_instruction),
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


def generate_trip_plan(
    trip: TripRequest,
    regeneration: TripRegenerationRequest | None = None,
) -> TripResponse:
    regeneration_instruction = None

    if regeneration is not None:
        regeneration_instruction = regeneration.regeneration_instruction

    content = _request_llm_content(trip, regeneration_instruction)
    return _parse_trip_response(content)
