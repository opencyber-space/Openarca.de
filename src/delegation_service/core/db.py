import os
import logging
from pymongo import MongoClient
from typing import List, Dict, Optional
from .schema import Delegation, DelegationStatus

from .delegation_tasks_pusher import NATSAPI


class DelegationRegistry:
    def __init__(self):
        db_url = os.getenv("DB_URL")
        client = MongoClient(db_url)
        self.collection = client["delegations_db"]["delegations"]

    def create_delegation(self, delegation: Delegation) -> bool:
        try:
            self.collection.insert_one(delegation.to_dict())
            logging.info(f"Delegation created: {delegation.delegation_id}")

            # push the delegation
            NATSAPI(nats_url=os.getenv("ORG_NATS_URL")).push_event(
                delegation.target_subject_id, delegation.sender_subject_id,
                event_type="delegation_task", event_data={
                    "task_id": delegation.task_id,
                    "sub_task_id": delegation.sub_task_id,
                    "delegation_id": delegation.delegation_id,
                    "data": delegation.sub_task_data
                }
            )

            return True
        except Exception as e:
            logging.error(f"Error creating delegation: {e}")
            return False

    def get_delegation(self, delegation_id: str) -> Optional[Delegation]:
        try:
            delegation_data = self.collection.find_one(
                {"delegation_id": delegation_id})
            if not delegation_data:
                return None
            return Delegation.from_dict(delegation_data)
        except Exception as e:
            logging.error(f"Error fetching delegation: {e}")
            raise

    def update_delegation(self, delegation_id: str, update_data: Dict) -> bool:
        try:
            result = self.collection.update_one(
                {"delegation_id": delegation_id}, {"$set": update_data}
            )
            if result.modified_count == 0:
                logging.warning(
                    f"No delegation found to update with ID: {delegation_id}")
                return False
            logging.info(f"Delegation updated: {delegation_id}")
            return True
        except Exception as e:
            logging.error(f"Error updating delegation: {e}")
            return False

    def delete_delegation(self, delegation_id: str) -> bool:
        try:
            result = self.collection.delete_one(
                {"delegation_id": delegation_id})
            if result.deleted_count == 0:
                logging.warning(
                    f"No delegation found to delete with ID: {delegation_id}")
                return False
            logging.info(f"Delegation deleted: {delegation_id}")
            return True
        except Exception as e:
            logging.error(f"Error deleting delegation: {e}")
            return False

    def query_delegations(self, query: Dict) -> List[Delegation]:
        try:
            delegations_cursor = self.collection.find(query)
            return [Delegation.from_dict(delegation) for delegation in delegations_cursor]
        except Exception as e:
            logging.error(f"Error querying delegations: {e}")
            raise

    def update_status(self, delegation_id: str, status_key: str, status_data: Dict) -> bool:
        try:
            status_obj = DelegationStatus.from_dict(status_data)
            result = self.collection.update_one(
                {"delegation_id": delegation_id}, {
                    "$set": {f"status.{status_key}": status_obj.to_dict()}}
            )
            if result.modified_count == 0:
                logging.warning(
                    f"No delegation found to update status with ID: {delegation_id}")
                return False
            logging.info(
                f"Delegation status updated for ID: {delegation_id}, Key: {status_key}")

            # push results:
            delegation = self.get_delegation(delegation_id)
            NATSAPI(nats_url=os.getenv("ORG_NATS_URL")).push_event(
                f"{delegation.sender_subject_id}__{delegation_id}", delegation.target_subject_id,
                event_type="delegation_result", event_data={
                    "task_id": delegation.task_id,
                    "sub_task_id": delegation.sub_task_id,
                    "delegation_id": delegation.delegation_id,
                    "data": status_data
                }
            )

            return True
        except Exception as e:
            logging.error(f"Error updating delegation status: {e}")
            return False
