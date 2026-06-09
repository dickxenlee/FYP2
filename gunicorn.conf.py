"""
Gunicorn configuration — auto-loaded by `gunicorn fyp_project.wsgi:application`
(Gunicorn looks for ./gunicorn.conf.py in the working directory by default).

This removes the need to pass any --flags in the Render Start Command.
"""
import os

# Bind to the port Render provides (falls back to 10000 locally).
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# LLM requests are slow. The default 30s timeout was SIGKILLing the worker
# mid-call and returning an HTML 502 page; 120s lets a normal Gemini call finish.
timeout = 120

# Free tier has limited RAM (~512MB): one worker with threads handles
# concurrent requests without running out of memory.
workers = 1
threads = 4

# Send access/error logs to stdout/stderr so they appear in the Render log tab.
accesslog = "-"
errorlog = "-"
