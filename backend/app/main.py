from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import llm, schemas
from app.crud import (
    build_saved_trip_detail,
    build_saved_trip_summary,
    create_trip,
    get_all_trips,
    get_trip_by_id,
)
from app.db import Base, engine, get_db

app = FastAPI(title="Trip Sketch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Welcome to the Trip Sketch API"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate-trip", response_model=schemas.TripResponse)
def generate_trip(
    trip: schemas.TripRequest,
    db: Session = Depends(get_db),
) -> schemas.TripResponse:
    try:
        trip_response = llm.generate_trip_plan(trip)
        create_trip(db, trip, trip_response)
        return trip_response
    except llm.LLMOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except llm.LLMUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except llm.LLMConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/trips", response_model=list[schemas.SavedTripSummary])
def read_trips(db: Session = Depends(get_db)) -> list[schemas.SavedTripSummary]:
    trips = get_all_trips(db)
    return [build_saved_trip_summary(trip) for trip in trips]


@app.get("/trips/{trip_id}", response_model=schemas.SavedTripDetail)
def read_trip(
    trip_id: int,
    db: Session = Depends(get_db),
) -> schemas.SavedTripDetail:
    trip = get_trip_by_id(db, trip_id)

    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found.")

    return build_saved_trip_detail(trip)


@app.post("/trips/{trip_id}/regenerate", response_model=schemas.TripResponse)
def regenerate_trip(
    trip_id: int,
    db: Session = Depends(get_db),
) -> schemas.TripResponse:
    saved_trip = get_trip_by_id(db, trip_id)

    if saved_trip is None:
        raise HTTPException(status_code=404, detail="Trip not found.")

    trip_request = schemas.TripRequest(
        destination=saved_trip.destination,
        number_of_days=saved_trip.number_of_days,
        budget=saved_trip.budget,
        interests=saved_trip.interests,
        travel_style=saved_trip.travel_style,
    )

    try:
        trip_response = llm.generate_trip_plan(trip_request)
        create_trip(db, trip_request, trip_response)
        return trip_response
    except llm.LLMOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except llm.LLMUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except llm.LLMConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
