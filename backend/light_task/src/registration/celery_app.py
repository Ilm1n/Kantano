from celery import Celery
from kombu import Exchange, Queue

from src.boards.models import BoardColumn, Task  # noqa: F401
from src.config import settings
from src.invitations.models import ProjectInvitation  # noqa: F401
from src.logger import setup_logging
from src.projects.models import Project, ProjectMember  # noqa: F401
from src.registration.models import OutboxEvent, PendingRegistration  # noqa: F401
from src.tags.models import Tag  # noqa: F401
from src.users.models import User  # noqa: F401

celery_app = Celery(
    "kantano",
    broker=settings.queue.broker_url,
    include=["src.registration.tasks"],
)
EMAIL_VERIFICATION_QUEUE = "email_verification"
EMAIL_VERIFICATION_EXCHANGE = Exchange(
    EMAIL_VERIFICATION_QUEUE,
    type="topic",
    durable=True,
)

celery_app.conf.update(
    broker_transport_options={"confirm_publish": True},
    broker_native_delayed_delivery_queue_type="classic",
    task_acks_late=True,
    task_default_delivery_mode="persistent",
    task_default_queue=EMAIL_VERIFICATION_QUEUE,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 5,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 1,
    },
    task_queues=(
        Queue(
            EMAIL_VERIFICATION_QUEUE,
            exchange=EMAIL_VERIFICATION_EXCHANGE,
            routing_key=EMAIL_VERIFICATION_QUEUE,
            durable=True,
            queue_arguments={"x-queue-type": "quorum"},
        ),
    ),
    task_reject_on_worker_lost=True,
    task_routes={"src.registration.tasks.*": {"queue": EMAIL_VERIFICATION_QUEUE}},
    task_send_sent_event=False,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_enable_remote_control=False,
    worker_prefetch_multiplier=1,
    worker_send_task_events=False,
    worker_detect_quorum_queues=True,
)

setup_logging()
