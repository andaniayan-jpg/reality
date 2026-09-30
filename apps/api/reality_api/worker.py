"""Production worker entry point; it uses database jobs and shared object storage."""

from __future__ import annotations

import time

from .config import Settings
from .database import Database
from .services import claim_next_job, process_job
from .storage import storage_from_settings


def run() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_url)
    storage = storage_from_settings(settings)
    database.create_all()
    while True:
        with database.sessions() as session:
            job_id = claim_next_job(session)
            if job_id:
                process_job(session, storage, settings, job_id)
        if not job_id:
            time.sleep(1)


if __name__ == "__main__":
    run()
