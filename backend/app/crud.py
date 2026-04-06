import json

from sqlalchemy.orm import Session

from app.models import Trip
from app.schemas import (
    DayPlan,
    SavedTripDetail,
    SavedTripSummary,
    TripRequest,
    TripResponse,
)


def create_trip(
    db: Session,
    trip_request: TripRequest,
    trip_response: TripResponse,
) -> Trip:
    trip = Trip(
        destination=trip_request.destination,
        number_of_days=trip_request.number_of_days,
        budget=trip_request.budget,
        interests=trip_request.interests,
        travel_style=trip_request.travel_style,
        title=trip_response.title,
        summary=trip_response.summary,
        notes=trip_response.notes,
        days_json=json.dumps([day.model_dump() for day in trip_response.days]),
    )

    db.add(trip)
    db.commit()
    db.refresh(trip)

    return trip


def get_all_trips(db: Session) -> list[Trip]:
    return db.query(Trip).order_by(Trip.created_at.desc(), Trip.id.desc()).all()


def get_trip_by_id(db: Session, trip_id: int) -> Trip | None:
    return db.query(Trip).filter(Trip.id == trip_id).first()


def _parse_days_json(days_json: str) -> list[DayPlan]:
    try:
        raw_days = json.loads(days_json)
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(raw_days, list):
        return []

    parsed_days: list[DayPlan] = []

    for day in raw_days:
        if not isinstance(day, dict):
            continue

        try:
            parsed_days.append(DayPlan.model_validate(day))
        except Exception:
            continue

    return parsed_days


def build_saved_trip_summary(trip: Trip) -> SavedTripSummary:
    return SavedTripSummary(
        id=trip.id,
        destination=trip.destination,
        number_of_days=trip.number_of_days,
        budget=trip.budget,
        interests=trip.interests,
        travel_style=trip.travel_style,
        title=trip.title,
        summary=trip.summary,
        notes=trip.notes,
        created_at=trip.created_at,
    )


def build_saved_trip_detail(trip: Trip) -> SavedTripDetail:
    summary = build_saved_trip_summary(trip)

    return SavedTripDetail(
        **summary.model_dump(),
        days=_parse_days_json(trip.days_json),
    )
