from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Trip Sketch API")


class TripRequest(BaseModel):
    destination: str
    number_of_days: int
    budget: str
    interests: str
    travel_style: str


class DayPlan(BaseModel):
    day: int
    plan: str


class TripResponse(BaseModel):
    title: str
    summary: str
    days: list[DayPlan]
    notes: str


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Welcome to the Trip Sketch API"}


@app.post("/generate-trip", response_model=TripResponse)
def generate_trip(trip: TripRequest) -> TripResponse:
    days = [
        DayPlan(
            day=day_number,
            plan=(
                f"Day {day_number} in {trip.destination}: enjoy a {trip.travel_style.lower()} "
                f"experience focused on {trip.interests.lower()} with a {trip.budget.lower()} budget."
            ),
        )
        for day_number in range(1, trip.number_of_days + 1)
    ]

    return TripResponse(
        title=f"{trip.number_of_days}-Day Trip to {trip.destination}",
        summary=(
            f"This is a mock travel plan for {trip.destination} designed for a "
            f"{trip.travel_style.lower()} trip with interests in {trip.interests.lower()}."
        ),
        days=days,
        notes=(
            "This is a sample response for now. Later, you can replace it with real trip "
            "generation logic, database storage, or an LLM integration."
        ),
    )
