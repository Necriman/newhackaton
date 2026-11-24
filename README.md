# Zinvest

Financial literacy in plain language for young people in Uzbekistan: short lessons
with quizzes, practice, an AI mentor, a cash-flow tracker and a workspace for
startup founders. Uzbek, Russian and English.

Live at [zinvest.uz](https://zinvest.uz).

## What's inside

- **Learning** — 11 units, 75 lessons, a quiz after every lesson, a study plan,
  daily practice, leagues and streaks.
- **Zinvest AI** — a finance-only mentor (Google Gemini).
- **Cash flow** — income and expenses, also from a Telegram bot.
- **Startup workspace** — market check, roadmap, team and task assignment with
  email notifications.
- **Admin panel** (`/admin-panel`) — users, content, moderation, AI usage,
  announcements, audit log, security; roles and two-factor sign-in.

## Stack

| Part | Tech |
| --- | --- |
| Backend | Django 6, plain JSON views, JWT (PyJWT) with rotating refresh cookies |
| Frontend | Vue 3, Vite 6, Tailwind CSS 4, vue-i18n |
| Database | PostgreSQL in production, SQLite for local development |
| AI | Google Gemini (`google-genai`) |
| Deploy | Docker Compose + Nginx, or Vercel (see `deploy/`) |

## Run locally

Requirements: Python 3.13+, Node.js 20+.

```bash
# backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env          # then edit it
python manage.py migrate
python manage.py loaddata course # the full course: 11 units, 75 lessons
python manage.py runserver

# frontend (second terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173, proxies /api to :8000
```

Make yourself an admin: register in the app, then

```bash
python manage.py set_staff_role you@example.com owner
```

and open `/admin-panel`.

Optional seed data: `seed_daily`, `seed_market` (daily questions and market
episodes for practice).

## Tests

```bash
cd backend && DEBUG=1 python manage.py test
```

## Configuration

All settings come from environment variables; `.env.example` lists the main
ones. Without `GEMINI_API_KEY` the AI features answer with a stub; without email
settings, letters are printed to the console.

## License

[MIT](LICENSE)
