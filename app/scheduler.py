from __future__ import annotations

import logging
import threading
import uuid

from app.agent.runner import AgentRunner
from app.config import Config

LOG = logging.getLogger(__name__)


def run_forever(config: Config, runner: AgentRunner) -> None:
    stop = threading.Event()
    LOG.info("Scheduler started; interval=%d minutes", config.interval_minutes)
    try:
        while not stop.is_set():
            result = runner.run_once(owner=str(uuid.uuid4()))
            if result == "limit":
                LOG.info("Scheduler stopped at MAX_DOCUMENTS=%d", config.max_documents)
                break
            stop.wait(config.interval_minutes * 60)
    except KeyboardInterrupt:
        LOG.info("Scheduler interrupted by user")
    finally:
        LOG.info("Scheduler stopped")
