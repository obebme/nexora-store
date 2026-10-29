import logging
import time

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .main import expire_unpaid_orders

POLL_INTERVAL_SECONDS = 30

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run() -> None:
    while True:
        try:
            with SessionLocal() as db:
                expired_count = expire_unpaid_orders(db)
            if expired_count:
                logger.info("Expired and released %s unpaid order reservations", expired_count)
        except SQLAlchemyError:
            logger.exception("Could not process expired order reservations")
        except HTTPException as error:
            logger.error(
                "Could not safely expire an order reservation: HTTP %s: %s",
                error.status_code,
                error.detail,
            )
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
