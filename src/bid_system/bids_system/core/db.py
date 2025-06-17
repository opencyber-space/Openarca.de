import os
import logging
from typing import Optional, List, Dict
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from dataclasses import asdict
from .schema import BidTasksDB, Bid, BidTaskResults

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BidTaskRegistryDB:
    def __init__(self):
        try:
            db_url = os.getenv("DB_URL")
            if not db_url:
                raise ValueError("DB_URL environment variable is not set.")
            self.client = MongoClient(db_url)
            self.db = self.client["BidTaskDB"]
            self.collection = self.db["BidTasks"]
            logger.info("Connected to MongoDB.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def create_bid_task(self, bid_task: BidTasksDB) -> bool:
        try:
            self.collection.insert_one(asdict(bid_task))
            logger.info(f"Bid task created with ID: {bid_task.bid_task_id}")
            return True
        except PyMongoError as e:
            logger.error(f"Error creating bid task: {e}")
            return False

    def get_bid_task(self, bid_task_id: str) -> Optional[BidTasksDB]:
        try:
            result = self.collection.find_one({"bid_task_id": bid_task_id})
            if result:
                logger.info(f"Bid task retrieved with ID: {bid_task_id}")
                return BidTasksDB.from_dict(result)
            logger.info(f"Bid task with ID: {bid_task_id} not found.")
            return None
        except PyMongoError as e:
            logger.error(f"Error retrieving bid task: {e}")
            return None

    def update_bid_task(self, bid_task_id: str, updated_data: dict) -> bool:
        try:
            result = self.collection.update_one(
                {"bid_task_id": bid_task_id},
                {"$set": updated_data}
            )
            if result.matched_count:
                logger.info(f"Bid task updated with ID: {bid_task_id}")
                return True
            logger.info(f"Bid task with ID: {bid_task_id} not found.")
            return False
        except PyMongoError as e:
            logger.error(f"Error updating bid task: {e}")
            return False

    def delete_bid_task(self, bid_task_id: str) -> bool:
        try:
            result = self.collection.delete_one({"bid_task_id": bid_task_id})
            if result.deleted_count:
                logger.info(f"Bid task deleted with ID: {bid_task_id}")
                return True
            logger.info(f"Bid task with ID: {bid_task_id} not found.")
            return False
        except PyMongoError as e:
            logger.error(f"Error deleting bid task: {e}")
            return False

    def list_bid_tasks(self) -> List[BidTasksDB]:
        try:
            tasks = self.collection.find()
            bid_tasks = [BidTasksDB.from_dict(task) for task in tasks]
            logger.info(f"{len(bid_tasks)} bid tasks retrieved.")
            return bid_tasks
        except PyMongoError as e:
            logger.error(f"Error listing bid tasks: {e}")
            return []

    def query_bid_tasks(self, query: Dict) -> List[BidTasksDB]:
        try:
            tasks = self.collection.find(query)
            bid_tasks = [BidTasksDB.from_dict(task) for task in tasks]
            logger.info(
                f"{len(bid_tasks)} bid tasks retrieved with query: {query}")
            return bid_tasks
        except PyMongoError as e:
            logger.error(f"Error querying bid tasks: {e}")
            return []


class BidRegistryDB:
    def __init__(self):
        try:
            db_url = os.getenv("DB_URL")
            if not db_url:
                raise ValueError("DB_URL environment variable is not set.")
            self.client = MongoClient(db_url)
            self.db = self.client["BidDB"]
            self.collection = self.db["Bids"]
            logger.info("Connected to MongoDB.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def create_bid(self, bid: Bid) -> bool:
        try:
            self.collection.insert_one(asdict(bid))
            logger.info(f"Bid created with ID: {bid.bid_id}")
            return True
        except PyMongoError as e:
            logger.error(f"Error creating bid: {e}")
            return False

    def get_bid(self, bid_id: str) -> Optional[Bid]:
        try:
            result = self.collection.find_one({"bid_id": bid_id})
            if result:
                logger.info(f"Bid retrieved with ID: {bid_id}")
                return Bid.from_dict(result)
            logger.info(f"Bid with ID: {bid_id} not found.")
            return None
        except PyMongoError as e:
            logger.error(f"Error retrieving bid: {e}")
            return None

    def update_bid(self, bid_id: str, updated_data: dict) -> bool:
        try:
            result = self.collection.update_one(
                {"bid_id": bid_id},
                {"$set": updated_data}
            )
            if result.matched_count:
                logger.info(f"Bid updated with ID: {bid_id}")
                return True
            logger.info(f"Bid with ID: {bid_id} not found.")
            return False
        except PyMongoError as e:
            logger.error(f"Error updating bid: {e}")
            return False

    def delete_bid(self, bid_id: str) -> bool:
        try:
            result = self.collection.delete_one({"bid_id": bid_id})
            if result.deleted_count:
                logger.info(f"Bid deleted with ID: {bid_id}")
                return True
            logger.info(f"Bid with ID: {bid_id} not found.")
            return False
        except PyMongoError as e:
            logger.error(f"Error deleting bid: {e}")
            return False

    def list_bids(self) -> List[Bid]:
        try:
            bids = self.collection.find()
            bid_list = [Bid.from_dict(bid) for bid in bids]
            logger.info(f"{len(bid_list)} bids retrieved.")
            return bid_list
        except PyMongoError as e:
            logger.error(f"Error listing bids: {e}")
            return []

    def query_bids(self, query: Dict) -> List[Bid]:
        try:
            bids = self.collection.find(query)
            bid_list = [Bid.from_dict(bid) for bid in bids]
            logger.info(f"{len(bid_list)} bids retrieved with query: {query}")
            return bid_list
        except PyMongoError as e:
            logger.error(f"Error querying bids: {e}")
            return []


class BidTaskResultsRegistry:
    def __init__(self):
        db_url = os.getenv("DB_URL")
        client = MongoClient(db_url)
        self.collection = client["bidding_db"]["bid_task_results"]

    def create_result(self, result: BidTaskResults) -> bool:
        try:
            self.collection.insert_one(result.to_dict())
            logging.info(f"Result created: {result.result_id}")
            return True
        except Exception as e:
            logging.error(f"Error creating result: {e}")
            return False

    def get_result(self, result_id: str) -> BidTaskResults:
        try:
            result_data = self.collection.find_one({"result_id": result_id})
            if not result_data:
                return None
            return BidTaskResults.from_dict(result_data)
        except Exception as e:
            logging.error(f"Error fetching result: {e}")
            raise

    def update_result(self, result_id: str, update_data: Dict) -> bool:
        try:
            result = self.collection.update_one(
                {"result_id": result_id}, {"$set": update_data})
            if result.modified_count == 0:
                logging.warning(
                    f"No result found to update with ID: {result_id}")
                return False
            logging.info(f"Result updated: {result_id}")
            return True
        except Exception as e:
            logging.error(f"Error updating result: {e}")
            return False

    def delete_result(self, result_id: str) -> bool:
        try:
            result = self.collection.delete_one({"result_id": result_id})
            if result.deleted_count == 0:
                logging.warning(
                    f"No result found to delete with ID: {result_id}")
                return False
            logging.info(f"Result deleted: {result_id}")
            return True
        except Exception as e:
            logging.error(f"Error deleting result: {e}")
            return False

    def query_results(self, query: Dict) -> List[BidTaskResults]:
        try:
            results_cursor = self.collection.find(query)
            return [BidTaskResults.from_dict(result) for result in results_cursor]
        except Exception as e:
            logging.error(f"Error querying results: {e}")
            raise
