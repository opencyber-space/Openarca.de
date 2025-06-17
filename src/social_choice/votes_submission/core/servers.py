import os
import threading
import asyncio
import logging
import json
from datetime import datetime

from flask import Flask, request, jsonify
from nats.aio.client import Client as NATS

from .schema import Votes
from .vote_pre_check import VoteAcceptor

logger = logging.getLogger("VoteServers")
logging.basicConfig(level=logging.INFO)


class VoteServers:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.vote_acceptor = VoteAcceptor(mongo_uri, db_name)
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.nats_url = os.getenv("ORG_NATS_URL", "nats://localhost:4222")

    def start_rest_server(self, host="0.0.0.0", port=8081):
        app = Flask("VoteREST")

        @app.route("/submit-vote", methods=["POST"])
        def submit_vote():
            try:
                data = request.get_json()
                vote = Votes.from_dict(data)
                vote.submission_time = datetime.utcnow()
                qualified = self.vote_acceptor.accept_vote(vote)
                return jsonify({"status": "accepted", "qualified": qualified}), 200
            except Exception as e:
                logger.exception("Failed to accept vote via REST")
                return jsonify({"error": str(e)}), 400

        threading.Thread(target=lambda: app.run(host=host, port=port, threaded=True), daemon=True).start()
        logger.info(f"REST server started on http://{host}:{port}/submit-vote")

    async def _nats_listener(self):
        nc = NATS()
        await nc.connect(servers=[self.nats_url])

        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                vote = Votes.from_dict(data)
                vote.submission_time = datetime.utcnow()
                qualified = self.vote_acceptor.accept_vote(vote)
                logger.info(f"Vote accepted via NATS. Qualified: {qualified}")
            except Exception as e:
                logger.exception("Failed to accept vote via NATS")

        await nc.subscribe("vote.submit", cb=message_handler)
        logger.info(f"Subscribed to NATS topic 'vote.submit' at {self.nats_url}")
        while True:
            await asyncio.sleep(1)

    def start_nats_server(self):
        threading.Thread(target=lambda: asyncio.run(self._nats_listener()), daemon=True).start()
        logger.info("NATS server started (subscriber to vote.submit)")

    def start_all(self):
        self.start_rest_server()
        self.start_nats_server()
