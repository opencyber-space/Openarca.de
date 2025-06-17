from nats.aio.client import Client as NATS
import asyncio
import logging
from typing import Dict


class EventsPusher:
    def __init__(self, nats_url: str):
        self.nats_url = nats_url
        self.nc = NATS()

    async def connect(self):
        try:
            await self.nc.connect(self.nats_url)
            logging.info("Connected to NATS")
        except Exception as e:
            logging.error(f"Error connecting to NATS: {e}")
            raise

    async def push(self, topic: str, message: Dict):
        try:
            if not self.nc.is_connected:
                await self.connect()
            await self.nc.publish(topic, str(message).encode('utf-8'))
            logging.info(f"Message published to topic {topic}: {message}")
        except Exception as e:
            logging.error(f"Error publishing message to NATS: {e}")
            raise

    async def disconnect(self):
        if self.nc.is_connected:
            await self.nc.close()
            logging.info("Disconnected from NATS")
