# Voice Khata

Voice Khata is a high-speed digital munim (clerk) for Indian kirana shops.
The shopkeeper speaks naturally in their own language mixed with English, and the AI accurately records udhaar, payments, partial payments, and due dates directly into the customer's khata.

## Architecture

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 async, Postgres, Pydantic v2, orjson.
- **Speech**: Swappable STT/TTS adapters (Sarvam AI, etc.).
- **NLU**: Fast-path deterministic rules engine (≤10ms) + guarded slow-path LLM fallback.
- **Frontend**: React + Vite + TypeScript PWA (AudioWorklet mic capture).

## Setup & Development

### Requirements
- Python 3.12 (`uv` package manager recommended)
- Docker Desktop (for Postgres)
- Node.js 20+

### Quickstart
1. Install dependencies:
   ```bash
   uv pip install -e ".[dev]"
   ```
2. Start Postgres:
   ```bash
   docker compose up -d
   ```
3. Run the cross-platform gate check:
   ```bash
   python scripts/check.py
   ```
