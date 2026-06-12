"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Simple In-memory Rate Limiter
# ─────────────────────────────────────────────────────────
_rate_windows: dict[str, deque] = defaultdict(deque)

def check_rate_limit(key: str):
    now = time.time()
    window = _rate_windows[key]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )
    window.append(now)

# ─────────────────────────────────────────────────────────
# Simple Cost Guard
# ─────────────────────────────────────────────────────────
_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

def check_and_record_cost(input_tokens: int, output_tokens: int):
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    _daily_cost += cost

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str


# ─────────────────────────────────────────────────────────
# Giao diện chat (HTML + JS thuần, không cần framework)
# ─────────────────────────────────────────────────────────
HTML_UI = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🇻🇳 Trợ Lý Du Lịch Việt Nam</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif;
         background: linear-gradient(135deg, #f6d365 0%, #fda085 100%);
         min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }
  .app { width: 100%; max-width: 520px; background: #fff; border-radius: 20px;
         box-shadow: 0 20px 60px rgba(0,0,0,.25); overflow: hidden; display: flex; flex-direction: column; height: 90vh; }
  header { background: linear-gradient(135deg, #c0392b, #e74c3c); color: #fff; padding: 18px 20px; }
  header h1 { font-size: 1.25rem; display: flex; align-items: center; gap: 8px; }
  header p { font-size: .8rem; opacity: .9; margin-top: 4px; }
  .key-row { background: #fff7e6; padding: 8px 20px; display: flex; gap: 8px; align-items: center; font-size: .8rem; border-bottom: 1px solid #f0e0c0; }
  .key-row input { flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 8px; font-size: .8rem; }
  #chat { flex: 1; overflow-y: auto; padding: 18px; background: #faf7f2; display: flex; flex-direction: column; gap: 12px; }
  .msg { max-width: 80%; padding: 11px 15px; border-radius: 16px; line-height: 1.5; font-size: .92rem; white-space: pre-wrap; }
  .bot { background: #fff; border: 1px solid #eee; align-self: flex-start; border-bottom-left-radius: 4px; }
  .user { background: #e74c3c; color: #fff; align-self: flex-end; border-bottom-right-radius: 4px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 18px; background: #faf7f2; }
  .chip { background: #fff; border: 1px solid #e74c3c; color: #e74c3c; border-radius: 20px;
          padding: 5px 12px; font-size: .78rem; cursor: pointer; }
  .chip:hover { background: #e74c3c; color: #fff; }
  form { display: flex; gap: 8px; padding: 14px 18px; border-top: 1px solid #eee; background: #fff; }
  input#q { flex: 1; padding: 12px 14px; border: 1px solid #ddd; border-radius: 24px; font-size: .95rem; outline: none; }
  button { background: #e74c3c; color: #fff; border: none; border-radius: 24px; padding: 0 20px; font-size: .95rem; cursor: pointer; }
  button:disabled { opacity: .5; cursor: not-allowed; }
</style>
</head>
<body>
  <div class="app">
    <header>
      <h1>🇻🇳 Trợ Lý Du Lịch Việt Nam</h1>
      <p>Hỏi mình về điểm đến, ẩm thực, lịch trình du lịch Việt Nam</p>
    </header>
    <div class="key-row">
      🔑 API Key: <input id="apikey" value="demo-key-123" />
    </div>
    <div id="chat">
      <div class="msg bot">Xin chào! 👋 Mình là Trợ Lý Du Lịch Việt Nam. Bạn muốn đi đâu chơi?</div>
    </div>
    <div class="chips">
      <span class="chip">Đi Đà Nẵng có gì chơi?</span>
      <span class="chip">Hội An buổi tối</span>
      <span class="chip">Ẩm thực Hà Nội</span>
      <span class="chip">Lịch trình miền Trung</span>
    </div>
    <form id="f">
      <input id="q" placeholder="Nhập câu hỏi du lịch..." autocomplete="off" />
      <button id="send" type="submit">Gửi</button>
    </form>
  </div>
<script>
  const chat = document.getElementById('chat');
  const form = document.getElementById('f');
  const q = document.getElementById('q');
  const send = document.getElementById('send');

  function add(text, who) {
    const d = document.createElement('div');
    d.className = 'msg ' + who;
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    return d;
  }

  async function ask(question) {
    add(question, 'user');
    const typing = add('Đang soạn câu trả lời...', 'bot');
    send.disabled = true;
    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json',
                   'X-API-Key': document.getElementById('apikey').value },
        body: JSON.stringify({ question })
      });
      const data = await res.json();
      if (res.ok) {
        typing.textContent = data.answer;
      } else if (res.status === 401) {
        typing.textContent = '🔒 Sai hoặc thiếu API key. Kiểm tra ô API Key phía trên.';
      } else if (res.status === 429) {
        typing.textContent = '⏳ Bạn hỏi nhanh quá! Vui lòng chờ một chút rồi thử lại.';
      } else {
        typing.textContent = '⚠️ Lỗi: ' + (data.detail || res.status);
      }
    } catch (e) {
      typing.textContent = '⚠️ Không kết nối được tới server.';
    } finally {
      send.disabled = false;
    }
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = q.value.trim();
    if (!text) return;
    q.value = '';
    ask(text);
  });

  document.querySelectorAll('.chip').forEach(c =>
    c.addEventListener('click', () => ask(c.textContent)));
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["UI"])
def home():
    """Giao diện chat Trợ Lý Du Lịch Việt Nam."""
    return HTML_UI


@app.get("/info", tags=["Info"])
def info():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    # Rate limit per API key
    check_rate_limit(_key[:8])  # use first 8 chars as key bucket

    # Budget check
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = llm_ask(body.question)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    checks = {"llm": "mock" if not settings.openai_api_key else "openai"}
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(_daily_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(_daily_cost / settings.daily_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
