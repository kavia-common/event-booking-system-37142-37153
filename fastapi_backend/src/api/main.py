from typing import AsyncGenerator, List

from fastapi import Depends, FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Booking, Event
from .schemas import Booking as BookingSchema
from .schemas import BookingCreate, Event as EventSchema
from .sse import sse_manager

app = FastAPI(
    title="Event Booking API",
    description="APIs for listing events and creating bookings with seat availability enforcement.",
    version="0.1.0",
    openapi_tags=[
        {"name": "Health", "description": "Health check endpoints"},
        {"name": "Events", "description": "Event listing and details"},
        {"name": "Bookings", "description": "Create and list bookings"},
        {"name": "Live Updates", "description": "Server-Sent Events for live seat availability"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # consider restricting in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create tables if they don't exist (idempotent for demo/dev environments)
Base.metadata.create_all(bind=engine)


@app.get("/", summary="Health Check", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}


@app.get(
    "/events/{event_id}/stream",
    response_class=PlainTextResponse,
    summary="Stream Event Seat Updates (SSE)",
    description="Open a Server-Sent Events (SSE) stream for a specific event to receive real-time seat availability updates. "
                "The response is a text/event-stream. Clients should reconnect on network interruption.",
    tags=["Live Updates"],
)
def stream_event_updates(
    event_id: int = Path(..., description="ID of the event to subscribe for updates"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Open an SSE stream for seat availability updates for a given event.

    Returns a StreamingResponse with 'text/event-stream' content-type.
    The stream yields messages whenever seat availability changes for this event.
    """
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    async def generator() -> AsyncGenerator[str, None]:
        # Emit initial state so the client knows current availability on subscribe
        initial_payload = {
            "event_id": event.id,
            "available_seats": event.available_seats,
            "total_seats": event.total_seats,
            "type": "initial",
        }
        import json as _json
        yield f"data: {_json.dumps(initial_payload)}\n\n"
        async for chunk in sse_manager.event_stream(event_id):
            yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get(
    "/docs/live-updates",
    summary="How to use Live Updates (SSE)",
    description="Returns a short usage note for connecting to the SSE endpoint from a frontend.",
    tags=["Live Updates"],
)
def sse_usage_note() -> dict:
    """Provide SSE client usage notes for documentation and quick testing."""
    return {
        "note": "Connect to /events/{event_id}/stream with EventSource in the browser.",
        "example_js": "const es = new EventSource(`${BASE_URL}/events/1/stream`); es.onmessage = (e) => console.log(JSON.parse(e.data));",
    }


@app.get(
    "/events",
    response_model=List[EventSchema],
    summary="List Events",
    description="Retrieve a list of all events.",
    tags=["Events"],
)
def list_events(db: Session = Depends(get_db)) -> List[EventSchema]:
    """Return all events."""
    events = db.execute(select(Event)).scalars().all()
    return events


@app.get(
    "/events/{event_id}",
    response_model=EventSchema,
    summary="Get Event by ID",
    description="Retrieve detailed information about a specific event by its ID.",
    tags=["Events"],
)
def get_event(
    event_id: int = Path(..., description="ID of the event"),
    db: Session = Depends(get_db),
) -> EventSchema:
    """Return the event with the given ID or 404."""
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@app.get(
    "/bookings",
    response_model=List[BookingSchema],
    summary="List Bookings",
    description="Retrieve all bookings.",
    tags=["Bookings"],
)
def list_bookings(db: Session = Depends(get_db)) -> List[BookingSchema]:
    """Return all bookings."""
    bookings = db.execute(select(Booking)).scalars().all()
    return bookings


@app.post(
    "/bookings",
    response_model=BookingSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create Booking",
    description="Create a booking for an event. This endpoint enforces seat availability and reduces available seats atomically.",
    tags=["Bookings"],
)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)) -> BookingSchema:
    """Create a new booking ensuring seats are available and decrement them.

    Seat enforcement logic:
    - Validate event exists.
    - Validate requested seats <= available seats.
    - Decrement available seats.
    - Create booking with simple reference value.
    All operations occur within a transaction.
    """
    # Get event
    event = db.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if payload.seats <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Seats must be > 0")

    if event.available_seats < payload.seats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough seats available",
        )

    try:
        # Adjust availability and persist booking within transaction
        event.available_seats -= payload.seats

        # Simple deterministic reference; consider UUID in production
        reference = f"EV{event.id}-S{payload.seats}-{event.available_seats}"

        booking = Booking(
            event_id=payload.event_id,
            user_name=payload.user_name,
            user_email=str(payload.user_email),
            seats=payload.seats,
            reference=reference,
        )
        db.add(booking)
        db.add(event)
        db.commit()
        db.refresh(booking)

        # After a successful booking and seat decrement, broadcast update to SSE subscribers
        try:
            # Fire-and-forget; if event loop not available (sync path), use asyncio
            import asyncio

            payload = {
                "event_id": event.id,
                "available_seats": event.available_seats,
                "total_seats": event.total_seats,
                "last_booking_id": booking.id,
                "type": "seat_update",
            }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule background task
                loop.create_task(sse_manager.broadcast(event.id, payload))
            else:
                loop.run_until_complete(sse_manager.broadcast(event.id, payload))
        except Exception:
            # Avoid breaking API flow on broadcast failures
            pass

        return booking
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking could not be created due to a data integrity error",
        )
