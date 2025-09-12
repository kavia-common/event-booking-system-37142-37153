# FastAPI Backend

## Introduction

This service exposes REST APIs for the Event Booking System. It integrates with a MySQL database, provides endpoints to list events, get event details, create bookings with seat enforcement, and stream live seat availability updates via Server-Sent Events (SSE). CORS is enabled for frontend access.

## Prerequisites

- Python 3.10+
- Virtual environment (recommended)
- Running MySQL instance with the Event Booking schema
  - Default local DB from the mysql_database container runs on port 5001
- Network access to the database host/port

## Install and Run

1. Create and activate a virtual environment:
   - python -m venv .venv
   - source .venv/bin/activate

2. Install dependencies:
   - pip install -r requirements.txt

3. Configure environment variables (see Environment). You can set variables in your shell or via a .env file:
   - Create a .env file in the fastapi_backend directory with:
     - MYSQL_URL=mysql+pymysql://appuser:dbuser123@localhost:5001/myapp
     - Or define the individual pieces (MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, MYSQL_HOST, MYSQL_PORT)

4. Start the server:
   - uvicorn src.api.main:app --host 0.0.0.0 --port 3001 --reload

5. Verify:
   - Health: http://localhost:3001/
   - Events: http://localhost:3001/events

## Ports

- Backend service runs on port 3001 by default when using the uvicorn command above.

## Environment

The backend reads the database configuration from environment variables in src/api/database.py.

- Preferred single URL:
  - MYSQL_URL (e.g., mysql+pymysql://user:pass@host:port/db)
- Or individual variables (MYSQL_URL takes precedence):
  - MYSQL_USER
  - MYSQL_PASSWORD
  - MYSQL_DB
  - MYSQL_PORT (default 3306 if not set)
  - MYSQL_HOST (default localhost if not set)

Example .env:

- MYSQL_URL=mysql+pymysql://appuser:dbuser123@localhost:5001/myapp

If you use a .env file, you can export it with:
- set -a; source .env; set +a

## API Overview

- GET / — Health check
- GET /events — List all events
- GET /events/{event_id} — Get event details by ID
- POST /bookings — Create a booking
- GET /bookings — List all bookings
- GET /events/{event_id}/stream — SSE stream for seat updates

OpenAPI
- A generated OpenAPI is available at interfaces/openapi.json. You can regenerate it via:
  - python -m src.api.generate_openapi

## Data Models (summary)

- Event: { id, title, description, date, total_seats, available_seats, price, created_at }
- Booking: { id, event_id, user_name, user_email, seats, reference, created_at }

## Booking Flow

1. Frontend requests POST /bookings with payload:
   - { event_id, user_name, user_email, seats }
2. Backend validates:
   - Event exists
   - seats > 0
   - event.available_seats >= seats
3. Backend decrements available_seats atomically and creates booking
4. Backend broadcasts an SSE update to subscribers of /events/{event_id}/stream

## Live Updates (SSE)

- Endpoint: GET /events/{event_id}/stream
- Returns text/event-stream
- On subscription:
  - Sends an initial payload with current availability
  - Streams updates whenever a booking is created (seat decrement)
- Frontend usage example:
  - const es = new EventSource("http://localhost:3001/events/1/stream");
  - es.onmessage = (e) => console.log(JSON.parse(e.data));

## Step-by-Step Setup

1. Ensure the mysql_database container has been started and the DB is reachable on port 5001 with schema applied.
2. Configure environment variables as above (prefer MYSQL_URL).
3. Install dependencies and start uvicorn on port 3001.
4. Test endpoints with curl:
   - curl http://localhost:3001/events
   - curl -X POST http://localhost:3001/bookings -H "Content-Type: application/json" -d '{"event_id":1,"user_name":"Alice","user_email":"alice@example.com","seats":1}'

## .env Usage

- Place a .env file in this directory for easy local development with:
  - MYSQL_URL=mysql+pymysql://appuser:dbuser123@localhost:5001/myapp
- Export variables before starting the server:
  - set -a; source .env; set +a
  - uvicorn src.api.main:app --host 0.0.0.0 --port 3001 --reload

## Troubleshooting

- Cannot connect to DB:
  - Verify MYSQL_URL or component envs are set correctly.
  - Confirm DB is reachable:
    - mysql -u appuser -pdbuser123 -h localhost -P 5001 myapp -e "SELECT 1;"
- ImportError: No module named 'pymysql':
  - Ensure requirements are installed: pip install -r requirements.txt
- CORS issues in browser:
  - CORS is wide open for development (allow_origins=["*"]). If modified for production, ensure the frontend origin is allowed.
- 400 Not enough seats available:
  - The capacity triggers are working. Reduce seats or choose a different event.
- SSE not updating:
  - Browser auto-reconnects on temporary errors.
  - Ensure the booking POST succeeds; backend emits the update on success.
- Port in use:
  - Change the uvicorn port: --port 3002

## Project Structure

- src/api/main.py — Application and endpoints
- src/api/database.py — DB session and URL assembly from environment
- src/api/models.py — SQLAlchemy models
- src/api/schemas.py — Pydantic schemas
- src/api/sse.py — In-memory SSE manager
- interfaces/openapi.json — Generated OpenAPI schema

## Notes

- Base.metadata.create_all(bind=engine) will create tables if they do not exist. In production, prefer migrations (e.g., Alembic).
