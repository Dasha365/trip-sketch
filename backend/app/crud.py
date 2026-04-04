import json

from sqlalchemy.orm import Session

from app.models import Trip
from app.schemas import TripRequest, TripResponse


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
