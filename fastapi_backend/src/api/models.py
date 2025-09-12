from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class Event(Base):
    """Event model representing an event with capacity and pricing."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(String(2048), nullable=True)
    date = Column(DateTime, nullable=False, index=True)
    total_seats = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    bookings = relationship("Booking", back_populates="event", cascade="all, delete-orphan")


class Booking(Base):
    """Booking model capturing reservations against an event."""

    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("event_id", "user_email", "reference", name="uq_event_user_reference"),
    )

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_name = Column(String(255), nullable=False)
    user_email = Column(String(255), nullable=False, index=True)
    seats = Column(Integer, nullable=False)
    reference = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    event = relationship("Event", back_populates="bookings")
