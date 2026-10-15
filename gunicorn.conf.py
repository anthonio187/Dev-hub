"""Gunicorn settings. Override any value with GUNICORN_* environment variables if needed."""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60            # GitHub/GitLab lookups have a 6s timeout each; leave headroom
graceful_timeout = 30
keepalive = 5
max_requests = 1000     # recycle workers to contain memory growth
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
forwarded_allow_ips = "*"   # behind Render/Railway/Fly proxies; ProxyFix is applied in app.py
