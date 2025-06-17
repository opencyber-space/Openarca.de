from core.servers import VoteServers
import time

if __name__ == "__main__":
    server = VoteServers()
    server.start_all()

    while True:
        time.sleep(10)
