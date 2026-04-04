from pydantic import BaseModel


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
