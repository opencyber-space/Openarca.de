import logging
import threading
from flask import Flask, request, jsonify
import asyncio
import json
from websockets import serve, WebSocketServerProtocol

from .queries import QueriesManager

logger = logging.getLogger("QueriesAPIServer")
logging.basicConfig(level=logging.INFO)

class QueriesAPIServer:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db", host="0.0.0.0", port=8082):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.host = host
        self.port = port
        self.manager = QueriesManager(mongo_uri, db_name)
        self.app = Flask("VotingQueriesAPI")
        self._register_routes()

    def _register_routes(self):
        app = self.app

        @app.route("/get-report/<social_task_id>", methods=["GET"])
        def get_report(social_task_id):
            try:
                result = self.manager.get_report(social_task_id)
                return jsonify(result), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 400

        @app.route("/generic-query/<collection_name>", methods=["POST"])
        def generic_query(collection_name):
            try:
                filters = request.get_json() or {}
                result = self.manager.generic_query(collection_name, filters)
                return jsonify(result), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 400

        @app.route("/get-status/<social_task_id>", methods=["GET"])
        def get_status(social_task_id):
            try:
                status = self.manager.get_status(social_task_id)
                return jsonify({"status": status}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 400

        @app.route("/get-full-task-bundle/<social_task_id>", methods=["GET"])
        def get_full_bundle(social_task_id):
            try:
                result = self.manager.get_full_task_bundle(social_task_id)
                return jsonify(result), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 400

        @app.route("/is-live-streaming-enabled/<social_task_id>", methods=["GET"])
        def check_live_streaming(social_task_id):
            try:
                enabled = self.manager.is_live_streaming_enabled(social_task_id)
                return jsonify({"enabled": enabled}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 400

    def run_in_thread(self):
        def _start():
            logger.info(f"Starting Queries API server at {self.host}:{self.port}")
            self.app.run(host=self.host, port=self.port, threaded=True)

        thread = threading.Thread(target=_start, daemon=True)
        thread.start()
        return thread


class LiveStreamWebSocketServer:
    def __init__(self, host="0.0.0.0", port=8765, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.host = host
        self.port = port
        self.manager = QueriesManager(mongo_uri, db_name)
        self.active_threads = {}

    async def handler(self, websocket: WebSocketServerProtocol):
        try:
            init_message = await websocket.recv()
            try:
                init_data = json.loads(init_message)
                task_id = init_data.get("social_task_id")
                refresh_interval = int(init_data.get("refresh_interval", 5))
                if not task_id:
                    await websocket.send(json.dumps({"error": "Missing social_task_id"}))
                    await websocket.close()
                    return
            except Exception:
                await websocket.send(json.dumps({"error": "Invalid request format. Must be JSON with 'social_task_id' and 'refresh_interval'"}))
                await websocket.close()
                return

            logger.info(f"New connection for social_task_id={task_id} with refresh interval={refresh_interval}")

            if not self.manager.is_live_streaming_enabled(task_id):
                await websocket.send(json.dumps({"error": "Live streaming not enabled for this task"}))
                await websocket.close()
                return

            stop_event = threading.Event()

            def stream_task():
                try:
                    while not stop_event.is_set():
                        try:
                            bundle = self.manager.get_full_task_bundle(task_id)
                            asyncio.run(websocket.send(json.dumps({"type": "update", "data": bundle})))
                        except Exception as e:
                            logger.warning(f"Streaming error for {task_id}: {e}")
                        stop_event.wait(refresh_interval)
                except Exception as e:
                    logger.exception(f"Stream thread crashed for task {task_id}: {e}")

            stream_thread = threading.Thread(target=stream_task, daemon=True)
            self.active_threads[websocket] = (stream_thread, stop_event)
            stream_thread.start()

            # Wait until the connection is closed
            await websocket.wait_closed()

        except Exception as e:
            logger.exception("WebSocket connection failed.")
        finally:
            # Clean up thread
            if websocket in self.active_threads:
                logger.info("Cleaning up background stream thread.")
                thread, stop_event = self.active_threads.pop(websocket)
                stop_event.set()

    def run_in_thread(self):
        def _start():
            logger.info(f"Starting WebSocket server at ws://{self.host}:{self.port}")
            asyncio.run(serve(self.handler, self.host, self.port))

        thread = threading.Thread(target=_start, daemon=True)
        thread.start()
        return thread
