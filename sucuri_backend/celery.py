import os

from celery import Celery
from kombu import Queue

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError("DJANGO_SETTINGS_MODULE environment variable is not set")

app = Celery("sucuri_backend")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

app.conf.task_queues = (
    Queue("critical", routing_key="critical"),
    Queue("default", routing_key="default"),
    Queue("bulk", routing_key="bulk"),
)
app.conf.task_default_queue = "default"
app.conf.task_queue_max_priority = 10

app.conf.task_routes = {
    "apps.scans.tasks.run_browser_scan": {"queue": "critical"},
    "apps.scans.tasks.trigger_scan": {"queue": "default"},
    "apps.scans.tasks.process_scan_result": {"queue": "default"},
    "apps.scans.tasks.generate_pdf_report": {"queue": "bulk"},
    "apps.agents.tasks.*": {"queue": "default"},
    "apps.domains.tasks.*": {"queue": "bulk"},
}
