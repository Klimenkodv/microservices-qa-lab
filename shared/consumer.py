from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from prometheus_client import Counter

from .events import UserRegisteredEvent, kafka_headers

CONSUMED = Counter("kafka_messages_consumed_total", "Consumed Kafka messages", ["service", "result"])
FAILURES = Counter("kafka_consumer_failures_total", "Consumer processing failures", ["service"])
DLQ = Counter("dlq_messages_total", "Messages sent to DLQ", ["service"])


async def consume_forever(
    *,
    service: str,
    bootstrap_servers: str,
    group_id: str,
    topic: str,
    dlq_topic: str,
    pause_event: asyncio.Event,
    ready_event: asyncio.Event,
    stop_event: asyncio.Event,
    handler: Callable[[UserRegisteredEvent], Awaitable[None]],
    logger: logging.Logger,
) -> None:
    while not stop_event.is_set():
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda value: json.loads(value.decode()),
        )
        producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
        try:
            await consumer.start()
            await producer.start()
            ready_event.set()
            async for message in consumer:
                await pause_event.wait()
                event = UserRegisteredEvent.model_validate(message.value)
                handled = False
                last_error = ""
                for attempt in range(1, 4):
                    try:
                        await handler(event)
                        handled = True
                        CONSUMED.labels(service, "success").inc()
                        break
                    except Exception as exc:
                        last_error = f"{type(exc).__name__}: {exc}"
                        FAILURES.labels(service).inc()
                        logger.error(
                            f"Consumer attempt {attempt}/3 failed",
                            extra={"event_id": event.event_id, "user_id": event.data.user_id, "email": event.data.email, "error_type": type(exc).__name__},
                        )
                        await asyncio.sleep(attempt)
                if not handled:
                    body = {"reason": last_error, "source_topic": topic, "payload": event.model_dump(mode="json")}
                    await producer.send_and_wait(
                        dlq_topic,
                        key=event.data.user_id.encode(),
                        value=json.dumps(body).encode(),
                        headers=kafka_headers(event),
                    )
                    DLQ.labels(service).inc()
                    CONSUMED.labels(service, "dlq").inc()
                    logger.error("Message sent to DLQ", extra={"event_id": event.event_id, "user_id": event.data.user_id, "email": event.data.email})
                await consumer.commit()
                if stop_event.is_set():
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            ready_event.clear()
            logger.error("Kafka consumer unavailable; retrying", extra={"error_type": type(exc).__name__})
            await asyncio.sleep(3)
        finally:
            try:
                await consumer.stop()
                await producer.stop()
            except Exception:
                pass
