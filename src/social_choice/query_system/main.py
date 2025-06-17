import time
import logging
from core.servers import QueriesAPIServer
from core.servers import LiveStreamWebSocketServer

logger = logging.getLogger("VotingQuerySystemMain")
logging.basicConfig(level=logging.INFO)


def main():
    logger.info("Launching Voting Query System...")

    rest_server = QueriesAPIServer()
    rest_thread = rest_server.run_in_thread()

    ws_server = LiveStreamWebSocketServer()
    ws_thread = ws_server.run_in_thread()

    logger.info("All servers started. System is live.")

    try:
        while True:
            time.sleep(2000)
    except KeyboardInterrupt:
        logger.info("Shutting down servers...")


if __name__ == "__main__":
    main()
