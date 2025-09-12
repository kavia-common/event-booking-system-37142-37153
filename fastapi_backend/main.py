import os
import re
from datetime import datetime
from typing import List, Optional

import mysql.connector
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr, validator

# FastAPI app with metadata and tags for OpenAPI
app = FastAPI(
    title="Event Booking Backend",
    description="FastAPI backend for events listing, event details, and booking creation. Integrates with MySQL.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Health", "description": "Service health and readiness"},
        {"name": "Events", "description": "Operations on events"},
        {"name": "Bookings", "description": "Operations on bookings"},
    ],
)

# CORS configuration - origin can be overridden via env if needed
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection settings via environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "events_db")

def get_db_connection():
    """
    Create a new MySQL connection using mysql-connector-python.
    This is intentionally not a global connection to avoid stale connections in serverless/async contexts.
    """
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=False,
        )
        return conn
    except mysql.connector.Error as e:
        # Re-raise as HTTPException for API consumers
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: {str(e)}",
        )

def db_dependency():
    """
    Dependency that yields a DB connection and ensures it is closed.
    """
    conn = get_db_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ----------------------
# Pydantic Schemas
# ----------------------

class EventBase(BaseModel):
    title: str = Field(..., description="Title of the event")
    description: Optional[str] = Field(None, description="Detailed description of the event")
    date_time: datetime = Field(..., description="Start date/time of the event (ISO format)")
    venue: str = Field(..., description="Venue for the event")
    total_seats: int = Field(..., ge=0, description="Total number of seats for the event")
    available_seats: int = Field(..., ge=0, description="Currently available seats")

class Event(EventBase):
    id: int = Field(..., description="Unique identifier of the event")
    created_at: Optional[datetime] = Field(None, description="Created timestamp")
    updated_at: Optional[datetime] = Field(None, description="Updated timestamp")

    class Config:
        orm_mode = True

class BookingBase(BaseModel):
    event_id: int = Field(..., description="ID of the event being booked")
    user_name: str = Field(..., min_length=1, description="Name of the user making the booking")
    user_email: EmailStr = Field(..., description="Email address of the user making the booking")
    seats_booked: int = Field(..., gt=0, description="Number of seats to book (> 0)")

class BookingCreate(BookingBase):
    pass

class Booking(BookingBase):
    id: int = Field(..., description="Unique identifier of the booking")
    status: str = Field(..., description="Booking status, e.g., CONFIRMED or CANCELLED")
    created_at: datetime = Field(..., description="Booking creation time")

    class Config:
        orm_mode = True

# ----------------------
# Routes
# ----------------------

# PUBLIC_INTERFACE
@app.get("/", tags=["Health"], summary="Health check", description="Returns service health status.")
def health_check():
    """Health check endpoint to verify the service is running."""
    return {"status": "ok", "service": "event-booking-backend", "version": "1.0.0"}

# PUBLIC_INTERFACE
@app.get("/events", response_model=List[Event], tags=["Events"], summary="List events", description="Retrieve a list of all events.")
def list_events(conn=Depends(db_dependency)):
    """Return a list of all events."""
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, title, description, date_time, venue, total_seats, available_seats, created_at, updated_at
            FROM events
            ORDER BY date_time ASC, id ASC
            """
        )
        rows = cursor.fetchall()
        events: List[Event] = []
        for r in rows:
            # mysql-connector may return datetime/date types already; ensure keys align to schema
            events.append(Event(**r))
        return events
    finally:
        cursor.close()

# PUBLIC_INTERFACE
@app.get("/events/{event_id}", response_model=Event, tags=["Events"], summary="Get event by ID", description="Retrieve details for a single event by ID.")
def get_event(event_id: int, conn=Depends(db_dependency)):
    """Return details for the specified event ID."""
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, title, description, date_time, venue, total_seats, available_seats, created_at, updated_at
            FROM events
            WHERE id = %s
            """,
            (event_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return Event(**row)
    finally:
        cursor.close()

def _get_event_for_update(conn, event_id: int):
    """
    Fetch the event row for update, locking it to prevent race conditions when booking seats.
    """
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, title, description, date_time, venue, total_seats, available_seats, created_at, updated_at
        FROM events
        WHERE id = %s
        FOR UPDATE
        """,
        (event_id,),
    )
    row = cursor.fetchone()
    return cursor, row

# PUBLIC_INTERFACE
@app.post(
    "/bookings",
    response_model=Booking,
    status_code=status.HTTP_201_CREATED,
    tags=["Bookings"],
    summary="Create booking",
    description="Create a new booking with validation: seats_booked > 0, email format, seats_booked <= available_seats.",
)
def create_booking(payload: BookingCreate, conn=Depends(db_dependency)):
    """
    Create a booking for an event with validation:
    - seats_booked must be > 0
    - user_email must be a valid email
    - seats_booked must be <= available_seats for the event
    On success, decreases available_seats and returns the created booking.
    """
    # Pydantic already validates EmailStr and seats_booked > 0 from model definitions.

    # Start transaction
    try:
        # Lock the event row to ensure accurate seat deduction
        lock_cursor, event_row = _get_event_for_update(conn, payload.event_id)
        if not event_row:
            lock_cursor.close()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

        available = int(event_row["available_seats"])
        if payload.seats_booked > available:
            lock_cursor.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested seats ({payload.seats_booked}) exceed available seats ({available}).",
            )

        # Deduct seats
        new_available = available - payload.seats_booked
        lock_cursor.execute(
            "UPDATE events SET available_seats = %s, updated_at = NOW() WHERE id = %s",
            (new_available, payload.event_id),
        )
        lock_cursor.close()

        # Create booking
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bookings (event_id, user_name, user_email, seats_booked, status, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (payload.event_id, payload.user_name, payload.user_email, payload.seats_booked, "CONFIRMED"),
        )
        booking_id = cursor.lastrowid
        conn.commit()
        cursor.close()

        # Fetch and return created booking
        get_cursor = conn.cursor(dictionary=True)
        get_cursor.execute(
            """
            SELECT id, event_id, user_name, user_email, seats_booked, status, created_at
            FROM bookings
            WHERE id = %s
            """,
            (booking_id,),
        )
        row = get_cursor.fetchone()
        get_cursor.close()
        if not row:
            # This should not happen, but handle gracefully
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load created booking")
        return Booking(**row)
    except HTTPException:
        # Propagate expected errors
        conn.rollback()
        raise
    except mysql.connector.Error as e:
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")

# PUBLIC_INTERFACE
@app.get(
    "/bookings",
    response_model=List[Booking],
    tags=["Bookings"],
    summary="List bookings",
    description="Retrieve a list of all bookings.",
)
def list_bookings(conn=Depends(db_dependency)):
    """Return a list of all bookings."""
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, event_id, user_name, user_email, seats_booked, status, created_at
            FROM bookings
            ORDER BY created_at DESC, id DESC
            """
        )
        rows = cursor.fetchall()
        bookings: List[Booking] = [Booking(**r) for r in rows]
        return bookings
    finally:
        cursor.close()
