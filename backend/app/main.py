from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import llm, schemas
from app.crud import create_trip
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
