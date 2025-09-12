# FastAPI Backend

FastAPI backend for the Event Booking system.

## Features
- Pydantic schemas for Event and Booking
- MySQL connection via environment variables
- API endpoints:
  - GET / (health)
  - GET /events
  - GET /events/{id}
  - POST /bookings
  - GET /bookings
- Booking validation:
  - seats_booked > 0 (handled by Pydantic)
  - user_email is a valid email (Pydantic EmailStr)
  - seats_booked <= available_seats (transactional check with row lock)

## Environment Variables
Set the following environment variables in the container environment (.env is handled by orchestrator):
- DB_HOST
- DB_PORT
- DB_USER
- DB_PASSWORD
- DB_NAME
- CORS_ORIGIN (optional, default: http://localhost:3000)

## Run locally
Install dependencies:
    pip install -r requirements.txt

Start server:
    uvicorn main:app --host 0.0.0.0 --port 3001

The API will be available at http://localhost:3001.

## Notes
- Requires the MySQL database container to be running and accessible with the provided credentials.
- Uses a simple connection-per-request pattern with transaction handling for seat updates.
