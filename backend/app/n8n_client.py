import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)


async def trigger_ingest_complete(batch_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                settings.N8N_WEBHOOK_URL,
                json={"batch_id": batch_id},
            )
            r.raise_for_status()
            logger.info("n8n webhook OK for batch %s", batch_id)
            return True
    except Exception as exc:
        logger.warning("n8n webhook failed for batch %s: %s", batch_id, exc)
        return False
