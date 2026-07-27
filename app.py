"""
Web app: chat UI for the sales team + JSON API.

Run:  ANTHROPIC_API_KEY=sk-... uvicorn app:app --host 0.0.0.0 --port 8000
Then share http://<host>:8000 with the team.

Endpoints:
  GET  /            chat UI
  POST /api/ask     {"question": "...", "user": "name"} -> structured answer
  GET  /api/digest  today's manager digest (protect before rollout)
"""

import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from agent import answer_question
from daily_summary import build_digest

app = FastAPI(title="Certinal RFP Agent")

# Shared team access code, set as an environment variable on the host.
# Not full authentication, but keeps the app and your API key from being
# used by anyone who stumbles on the URL. Per-user login is a later upgrade.
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")


def check_access(x_access_code: str | None):
    if not ACCESS_CODE:
        raise HTTPException(500, "Server misconfigured: ACCESS_CODE is not set.")
    if x_access_code != ACCESS_CODE:
        raise HTTPException(401, "Invalid access code.")


class AskRequest(BaseModel):
    question: str
    user: str = "unknown"


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/ask")
def ask(req: AskRequest, x_access_code: str | None = Header(default=None)):
    check_access(x_access_code)
    return answer_question(question=req.question, user=req.user)


@app.get("/api/digest", response_class=PlainTextResponse)
def digest(x_access_code: str | None = Header(default=None)):
    check_access(x_access_code)
    return build_digest()
