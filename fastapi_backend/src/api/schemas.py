from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, EmailStr, conint


# PUBLIC_INTERFACE
class EventBase(BaseModel):
    """Shared fields for events."""
    title: str = Field(..., description="Title of the event")
    description: Optional[str] = Field(None, description="Detailed description of the event")
    date: datetime = Field(..., description="Event date and time")
    total_seats: conint(ge=0) = Field(..., description="Total seats available for this event")
    available_seats: conint(ge=0) = Field(..., description="Remaining seats available for booking")
    price: float = Field(..., description="Ticket price")


class Event(EventBase):
    """Event response model."""
    id: int = Field(..., description="Unique event ID")

    class Config:
        from_attributes = True


# PUBLIC_INTERFACE
class BookingCreate(BaseModel):
    """Payload for creating a booking."""
    event_id: int = Field(..., description="ID of the event to book")
    user_name: str = Field(..., description="Name of the user booking the event")
    user_email: EmailStr = Field(..., description="Email of the user booking the event")
    seats: conint(gt=0) = Field(..., description="Number of seats to book")


class Booking(BaseModel):
    """Booking response model."""
    id: int = Field(..., description="Unique booking ID")
    event_id: int = Field(..., description="Event ID")
    user_name: str = Field(..., description="User name")
    user_email: EmailStr = Field(..., description="User email")
    seats: int = Field(..., description="Seats booked")
    reference: str = Field(..., description="Booking reference")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True
