# Project W API - Multimedia Library Backend

This is the Python backend API for the Multimedia Library Application. Built with **FastAPI**, it serves as the core layer managing database records, external media providers (such as TMDB), user libraries, authentication, and social features (reviews, lists, comments).

---

## 🛠️ Tech Stack & Features

- **FastAPI**: Modern, fast web framework for building APIs with Python 3.10+.
- **SQLAlchemy 2.0 & PostgreSQL**: Object-Relational Mapping (ORM) and robust data persistence.
- **Alembic**: Database migrations management.
- **Security & Auth**:
  - Argon2id password hashing using `argon2-cffi`.
  - Double-token JWT auth: 15-minute Access Tokens and 30-day rotating Refresh Tokens (stored as secure cookies and hashed in the database).
  - Rate limiting backed by Redis.
- **Media Catalog**:
  - Supports multiple media formats: `MOVIE`, `SERIES`, `BOOK`, `GAME`, `ALBUM`, `TRACK`.
  - Multi-provider metadata synchronization (e.g., TMDB wrapper implementation).
  - Fuzzy text searching enabled via PostgreSQL trigram indexes (`pg_trgm`).
  - Strict logic preventing duplicate media inserts.
- **Structured JSON Logging**: Centralized telemetry with request ID correlation.
- **Testing**: Complete testing coverage with `pytest` for mock authentication, database repositories, services, and router endpoints.

---

## 📁 File Structure

```
multimedia-library-api/
├── alembic/                 # Migration environment & versions
│   └── versions/            # PostgreSQL database migration scripts
├── app/                     # Main source code
│   ├── core/                # Configuration, logging, rate limiting, and middleware
│   ├── models/              # SQLAlchemy model definitions (User, Media, Review, etc.)
│   ├── providers/           # Third-party metadata integration (e.g. TMDB client)
│   ├── repositories/        # Database Access Object layer (DAO pattern)
│   ├── routers/             # API Router endpoints grouped by resource
│   ├── schemas/             # Pydantic serialization & validation schemas
│   ├── services/            # Business logic layer
│   └── database.py          # SQLAlchemy Session/Engine setup
├── docs/                    # Design documentation & API guidelines
├── postman/                 # API client testing collection
├── tests/                   # Pytest test suite
├── .env.example             # Template for configuration settings
├── alembic.ini              # Alembic config file
├── requirements.txt         # Package dependencies
└── TODO.md                  # Development road-map/tasks
```

---

## ⚙️ Configuration (.env)

Duplicate `.env.example` to `.env` and adjust the variables as required:

| Parameter | Description | Default |
| :--- | :--- | :--- |
| `APP_NAME` | Name of the FastAPI application | `Project W API` |
| `APP_ENV` | Environment state (`local`, `test`, `staging`, `production`) | `local` |
| `APP_BASE_URL` | Base URL of the API server | `http://localhost:8000` |
| `API_PREFIX` | Prefix for all router endpoints | `/api/v1` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://postgres:postgres@localhost:5432/project_w` |
| `JWT_SECRET_KEY` | Key used to sign JWT tokens (Must be strong in production) | `replace-with-a-long-random-secret` |
| `PASSWORD_PEPPER` | Secret pepper appended to passwords before hashing | `replace-with-a-long-random-pepper` |
| `REDIS_URL` | Redis URL for rate limiting and cache storage | `redis://localhost:6379/0` |
| `TMDB_API_KEY` | API credentials for TMDB integration | *None* |
| `CLOUDFLARE_R2_*` | R2 account ID, S3 credentials, and private bucket | *None* |

---

## 🚀 Setup & Running Locally

### 1. Set Up Virtual Environment
Activate Python environment:
```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Database Migration
Ensure PostgreSQL is running and the database matches your `DATABASE_URL` in `.env`.
Initialize tables using Alembic:
```bash
alembic upgrade head
```

### 4. Run Dev Server
Start the Uvicorn server in reload mode:
```bash
uvicorn app.main:app --reload
```
By default, the server runs on [http://localhost:8000](http://localhost:8000).

- **API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **System Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧪 Testing

The backend includes database-agnostic tests using SQLite in-memory databases for local development verification.

Run all tests via `pytest`:
```bash
pytest
```

To run with verbose output:
```bash
pytest -v
```

---

## Provider seeding

Providers are configured through `.env`; no provider secret is logged. Run seed pages from a dedicated worker or scheduler, never from an API request:

```bash
python -m scripts.run_seed --provider tmdb --media-type MOVIE --seed-kind popular --cursor 1 --limit 2
python -m scripts.run_seed --provider rawg --media-type GAME --seed-kind popular --cursor 1 --limit 2
python -m scripts.run_seed --provider open_library --media-type BOOK --seed-kind classics --cursor 1 --limit 2
```

Seed pages are idempotent by provider, media type, seed kind, and cursor. Spotify deliberately has no seed command and is used only for on-demand album/track search.

---

## Profile-image uploads

Profile images are authenticated, limited to JPEG/PNG/WebP, validated from their magic bytes, decoded with a pixel/dimension limit, and re-encoded to WebP before entering R2. Keep the R2 bucket private; owners retrieve images through the API.

```text
POST   /api/v1/uploads/profile-image   multipart/form-data field: file
GET    /api/v1/uploads/{upload_id}/content
DELETE /api/v1/uploads/{upload_id}
```

Apply the migration after adding the R2 configuration:

```bash
alembic upgrade head
```
