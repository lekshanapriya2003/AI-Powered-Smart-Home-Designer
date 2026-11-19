# Setup guide

Everything here is free and runs locally. No Docker.

## 1. Prerequisites

- **Python 3.10 or newer** (check with `python --version`)
- **Node.js 18 or newer** (check with `node --version`)
- **PostgreSQL 14 or newer**, installed locally (section 2)
- Free accounts for Google AI Studio, Groq and Cloudflare (section 4)

## 2. Install PostgreSQL

**Windows**
1. Download the installer from https://www.postgresql.org/download/windows/ and run it.
2. Keep the default port `5432`. Set a password for the `postgres` user and remember it.
3. The installer sets PostgreSQL up as a service that starts with Windows. You can skip Stack Builder.

**Mac**
```
brew install postgresql@16
brew services start postgresql@16
```
Homebrew installs it without a password for your own user. The simplest way to keep the instructions below working is to set one:
```
psql postgres -c "ALTER USER postgres PASSWORD 'yourpassword';"
```
If that says the role `postgres` does not exist, run `createuser -s postgres` first. Postgres.app (https://postgresapp.com) is a fine alternative.

**Linux (Ubuntu or Debian)**
```
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'yourpassword';"
```

Check it works: `psql -U postgres -h localhost -c "SELECT 1;"` (it asks for the password).

## 3. Create the database

You can skip this step. `scripts/init_db.py` creates the `smart_home_designer` database if it does not exist. To create it yourself:
```
psql -U postgres -h localhost -c "CREATE DATABASE smart_home_designer;"
```

## 4. Get the free API keys

**Gemini (primary LLM)**
1. Open https://aistudio.google.com/apikey and sign in with a Google account.
2. Click **Create API key** and copy it.
3. Free-tier limits are shown in your AI Studio project and can change. Google may use free-tier content to improve its products, so do not enter private data.

**Groq (fallback LLM)**
1. Open https://console.groq.com/keys and sign up.
2. Click **Create API Key** and copy it.
3. Free-tier limits depend on the model. See https://console.groq.com/settings/limits. The app generates one concept per request to stay small.

**Cloudflare Workers AI (images)**
1. Create a free account at https://dash.cloudflare.com.
2. Find your **Account ID** on the dashboard (it is also in the URL after you sign in).
3. Go to **AI**, then **Workers AI**, then **Use REST API**, then **Create a Workers AI API Token**. Copy the token.
4. The free allowance is 10,000 neurons per day, reset at 00:00 UTC. One FLUX schnell image costs roughly 40 to 60 neurons.

**Pollinations.ai** needs no key. It is used automatically if Cloudflare is not set up or fails.

You need at least one LLM key (Gemini or Groq). Having both is better, because then a rate limit on one does not stop the app.

## 5. Create the backend `.env`

```
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Edit `backend/.env`:
```
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/smart_home_designer
GEMINI_API_KEY=...
GROQ_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
GROQ_MODEL=openai/gpt-oss-120b
LLM_TIMEOUT_SECONDS=180
LLM_MAX_RETRIES=2
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
IMAGE_DIR=generated_images
FRONTEND_ORIGIN=http://localhost:5173
```
If your password has special characters such as `@` or `#`, URL-encode them (`@` becomes `%40`). `.env` is in `.gitignore`. Never commit it.

## 6. Create the tables

From `backend/`:
```
python scripts/init_db.py
```
Expected output: `Tables ready: design_images, design_requests, designs`. It is safe to run again, and it also adds any columns that were introduced after the first version.

## 7. Run the backend

```
uvicorn app.main:app --reload
```
Open http://localhost:8000/api/health. You should see `{"status":"ok","database":"connected"}`. The interactive API page is at http://localhost:8000/docs.

## 8. Run the frontend

In a second terminal:
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. If your backend is not at `http://localhost:8000`, copy `frontend/.env.example` to `frontend/.env` and change `VITE_API_URL`.

## 9. Run the tests

```
cd backend
pytest -v
```
These tests need no database or API keys.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing DATABASE_URL` on start | `backend/.env` does not exist or is empty. Copy `.env.example` to `.env` inside `backend/`. |
| `password authentication failed` | The password in `DATABASE_URL` is wrong. Reset it with the `ALTER USER` command in section 2. |
| `Could not connect to PostgreSQL` | PostgreSQL is not running or not on port 5432. Start the service (`brew services start ...`, `sudo systemctl start postgresql`, or Windows Services). |
| `pip install` fails on `psycopg2-binary` | Upgrade pip (`python -m pip install -U pip`) and use Python 3.10 to 3.13. |
| `column parent_request_id does not exist` | Your database was created in an earlier phase. Run `python scripts/init_db.py` again. |
| Browser shows "Cannot reach the backend" | The backend is not running, or `VITE_API_URL` is wrong. Check http://localhost:8000/api/health. |
| CORS error in the browser console | Open the app at `http://localhost:5173` or `http://127.0.0.1:5173`, and keep `FRONTEND_ORIGIN` in `.env` matching. |
| 503 "All LLM providers failed" | Missing or wrong keys, or both free quotas are used up. The error text names each provider. Wait a minute and retry. |
| Gemini error 404 mentioning the model | The model name was retired. Set `GEMINI_MODEL` in `.env` to a current Flash model from the AI Studio docs. |
| 502 "could not produce a valid floor plan" | The LLM kept returning invalid plans. Click generate again, or raise `LLM_MAX_RETRIES` in `.env` to 3 or 4. The backend terminal logs every rejected attempt and the reason, which shows what the LLM keeps getting wrong. |
| Images never appear | Check the Cloudflare ID and token. Without them Pollinations is used, which is slow (about 15 seconds per image) and can fail. Click the button again to retry the missing ones. |
| Port 8000 or 5173 already in use | Stop the other program. The frontend must stay on 5173 because the backend CORS setting expects it. |
| PowerShell blocks `activate` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use Command Prompt. |
