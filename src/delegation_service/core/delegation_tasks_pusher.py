import asyncio
import json
from nats.aio.client import Client as NATS


class NATSAPI:
    def __init__(self, nats_url):
        self.nats_url = nats_url
        self.nats_client = NATS()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect())

    async def _connect(self):
        try:
            await self.nats_client.connect(self.nats_url, loop=self._loop)
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to NATS at {self.nats_url}: {str(e)}")

    async def _publish(self, topic, message):
        try:
            await self.nats_client.publish(topic, json.dumps(message).encode('utf-8'))
        except Exception as e:
            raise RuntimeError(f"Failed to publish message to NATS: {str(e)}")

    def push_event(self, topic, sender_subject_id: str, event_type, event_data):
    
        message = {
            "event_type": event_type,
            "event_data": event_data,
            "sender_subject_id": sender_subject_id
        }

        try:
            self._loop.run_until_complete(self._publish(topic, message))
        except Exception as e:
            raise RuntimeError(
                f"Error while pushing delegation event: {str(e)}")

    def close(self):
        try:
            self._loop.run_until_complete(self.nats_client.close())
        except Exception as e:
            raise RuntimeError(f"Failed to close NATS connection: {str(e)}")
        finally:
            self._loop.stop()
            self._loop.close()
