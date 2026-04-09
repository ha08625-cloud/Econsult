## Stack
A Python/FastAPI backend with a React frontend, Postgres database, deployed on Railway.


## The slightly fuller description
"A single-container Railway deployment. The frontend is React built with Vite, served as static files by the Python backend. The API is FastAPI. The database is Postgres accessed via psycopg2 with Alembic managing migrations. There are also background workers for PDF generation and email delivery."


## The full stack, layer by layer
### Frontend

React (TypeScript)
Vite as the build tool
Two separate entry points: the patient-facing form, and the admin portal

### Backend

Python
FastAPI as the web framework — this is what handles HTTP requests and routes them to the right code
Uvicorn as the server — this is the process that actually listens for incoming connections and hands them to FastAPI

### Database

Postgres
psycopg2 as the connector (the library that speaks to Postgres)
Alembic for migrations

### Background workers

A PDF worker (generates PDFs from submissions)
A delivery worker (handles email sending and retries)
These run as separate processes, not as part of the main API

### Deployment

Single Docker container on Railway
Multi-stage Docker build — Node builds the frontend, Python runs everything
Railway also provisions the Postgres instance