# Day 12 Lab — Mission Answers

> **Sinh viên:** Lê Xuân Tiến Đạt
> **MSSV:** 2A202600549
> **Repo:** https://github.com/datlxt/Day12-2A202600549-LeXuanTienDat
> **Public URL:** https://day12-2a202600549-lexuantiendat.onrender.com

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns tìm được trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secret** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL` nằm thẳng trong code → push GitHub là lộ key.
2. **Không có config management** — `DEBUG = True`, `MAX_TOKENS = 500` cứng trong code, không đổi được theo môi trường.
3. **Dùng `print()` thay logging và log cả secret** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` → rò rỉ key ra log.
4. **Không có health check endpoint** — platform không biết khi nào app chết để restart.
5. **Port/host cố định + reload** — `host="localhost", port=8000, reload=True` → không chạy được trong container, không nhận `PORT` từ cloud.

### Exercise 1.3: Bảng so sánh Develop vs Production

| Feature | Develop (❌) | Production (✅) | Tại sao quan trọng? |
|---------|-------------|----------------|---------------------|
| Config | Hardcode trong code | `os.getenv(...)` từ env | Dễ đổi giữa dev/prod, không commit secret |
| Secrets | `OPENAI_API_KEY = "sk-..."` | Đọc từ environment | Không lộ key khi push GitHub |
| Health check | Không có | `GET /health` + `/ready` | Platform restart container khi fail, biết khi nào sẵn sàng nhận traffic |
| Logging | `print()` (lộ secret) | JSON có cấu trúc, không log secret | Dễ parse/search trong log aggregator |
| Bind/Port | `localhost:8000` cứng | `0.0.0.0` + `PORT` từ env | Chạy được trong container, nhận port cloud cấp |
| Shutdown | Tắt đột ngột | Graceful (SIGTERM + lifespan) | Không làm rớt request đang xử lý |

**Nguyên tắc cốt lõi: 12-Factor App** — config (secret, port, debug) phải nằm trong environment variable, không nằm trong code.

---

## Part 2: Docker

### Exercise 2.1: Trả lời câu hỏi Dockerfile

1. **Base image:** `python:3.11` (bản develop, full ~1GB) / `python:3.11-slim` (bản production, gọn hơn).
2. **Working directory:** `/app` — nơi chứa code trong container.
3. **Tại sao COPY requirements.txt trước:** tận dụng **layer cache** của Docker — khi chỉ sửa code (không đổi thư viện), Docker không cài lại dependencies → build lại rất nhanh.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, **dễ bị ghi đè** khi `docker run ... <lệnh khác>`; `ENTRYPOINT` là lệnh cố định luôn chạy.

### Exercise 2.3: So sánh image size (đo thực tế)

| Image | Cấu hình | Size |
|-------|----------|------|
| `agent-develop` | single-stage, `python:3.11` full | **1.66 GB** |
| `agent-production` | multi-stage, `python:3.11-slim` | **236 MB** |
| **Chênh lệch** | | **giảm ~86% (~7 lần)** |

**Vì sao nhỏ hơn:** base `slim` + multi-stage (Stage 1 builder có gcc/build tools → Stage 2 runtime chỉ copy package đã cài, vứt rác build). Image nhỏ → deploy nhanh, ít lỗ hổng bảo mật.

### Exercise 2.4: Architecture stack (docker-compose)

```
Client → Nginx (port 80) → Agent (port 8000) → Redis (cache/session)
```
Agent không expose port trực tiếp, chỉ giao tiếp qua Nginx; Redis lưu state để stateless.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy

- **Platform thực tế dùng:** Render (gói Free, không cần thẻ tín dụng). Ban đầu thử Railway nhưng workspace bị giới hạn đòi gắn thẻ.
- **Public URL:** https://day12-2a202600549-lexuantiendat.onrender.com
- **Cách deploy:** kết nối GitHub repo → Root Directory `06-lab-complete` → runtime Docker → set env vars → Render build Dockerfile và chạy.

### So sánh `railway.toml` vs `render.yaml`

| | railway.toml | render.yaml |
|---|---|---|
| Phong cách | Tối giản (start command + health) | Infrastructure-as-Code đầy đủ |
| Khai báo | startCommand, healthcheckPath, restartPolicy | type, runtime, region, plan, envVars, healthCheckPath, **autoDeploy** |
| Điểm chung | Đều dùng `$PORT` do platform cấp + healthcheck `/health` | |

**Bài học:** cả 2 đều cần app đọc `os.getenv("PORT")` và có endpoint `/health` — đúng những gì làm ở Part 1.

---

## Part 4: API Security

### Exercise 4.1–4.3: Kết quả test (auth + rate limit)

| Ca test | Kết quả |
|---------|---------|
| `/ask` không có API key | **401 Unauthorized** |
| `/ask` sai key | **403 Forbidden** |
| `/ask` đúng key | **200 OK** + câu trả lời |
| Spam > 10 request/phút | **429 Too Many Requests** (request 11+ bị chặn) |

Lớp bảo vệ theo thứ tự: **Auth (401/403) → Rate limit (429) → Cost guard (402/503)**.

### Exercise 4.4: Cost guard

Cộng dồn chi phí token ước tính theo ngày; nếu vượt `DAILY_BUDGET_USD` → trả **402 Payment Required** (per-user) hoặc **503** (global). Tự reset sang ngày mới. Mục đích: chống hóa đơn LLM bất ngờ kể cả khi có người lọt qua auth + rate limit. Thuật toán rate limit dùng **sliding window** (đếm request trong cửa sổ 60 giây).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health vs Readiness

- **`/health` (liveness):** "app còn sống không?" — fail → platform **restart** container. Test trả 200.
- **`/ready` (readiness):** "sẵn sàng nhận traffic chưa?" — fail → load balancer **ngừng route** (không giết). Trả 503 khi đang khởi động/shutdown.

### Exercise 5.2: Graceful shutdown (quan sát thực tế)

Nhấn Ctrl+C / gửi SIGTERM, log in ra:
```
🔄 Graceful shutdown initiated...
✅ Shutdown complete
Received signal ... — uvicorn will handle graceful shutdown
```
Quy trình: đặt `_is_ready = False` → `/ready` trả 503 (LB ngừng gửi request mới) → đợi `_in_flight_requests == 0` (tối đa 30s) → mới tắt → không rớt request đang xử lý.

### Exercise 5.3: Stateless design

State (lịch sử hội thoại) **không lưu trong RAM** mà lưu vào **Redis** — vì khi scale nhiều instance, mỗi instance có RAM riêng, load balancer chia request lung tung → lưu RAM sẽ mất ngữ cảnh. Redis là kho chung nên bất kỳ instance nào cũng đọc được.

### Exercise 5.4: Load balancing

`nginx.conf` dùng `upstream` round-robin chia traffic ra nhiều instance + `proxy_next_upstream` tự né instance hỏng (`docker compose up --scale agent=3`).

---

## Tổng kết

Đã hoàn thành toàn bộ Part 1–6: hiểu dev vs production, containerize multi-stage, deploy cloud có public URL, bảo mật API (auth + rate limit + cost guard), và thiết kế reliable (health/ready + graceful shutdown + stateless). Final project là **Trợ Lý Du Lịch Việt Nam** có giao diện chat, chạy live tại URL trên.
