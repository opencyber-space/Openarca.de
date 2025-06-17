import os
import asyncio
from typing import Dict, Union
from .schema import BidTasksDB, Bid
from .db import BidTaskRegistryDB, BidRegistryDB
from .events import EventsPusher

from .dsl_executor import new_dsl_workflow_executor, parse_dsl_output

import time


def create_bidding_task(bid_task_data: Dict) -> Dict:

    # Define required fields and their expected types
    required_fields = {
        "bid_task_data": dict,
        "bid_task_type": str,
        "bid_task_creator_subject": str,
        "bid_task_expiry_time": int,
        "bid_task_initiator_subject_id": str,
    }
    optional_fields = {
        "bid_task_eval_dsl_id": str,
        "bid_task_pqt_check_dsl_id": str,
        "bid_task_post_evaluation_id": str,
        "bid_involved_subjects": list,
    }

    async def _push_events(events_pusher, bidding_data: BidTasksDB):
        try:
            for subject_id in bidding_data.bid_involved_subjects:
                topic = f"{subject_id}_bid_events"
                await events_pusher.push(topic, bidding_data.to_dict())
        except Exception as e:
            raise e

    events_pusher = EventsPusher(nats_url=os.getenv("NATS_URL"))

    # Validate required fields
    for field, expected_type in required_fields.items():
        if field not in bid_task_data:
            return {"success": False, "message": f"Missing required field: {field}"}
        if not isinstance(bid_task_data[field], expected_type):
            return {
                "success": False,
                "message": f"Invalid type for field '{field}': "
                           f"expected {expected_type.__name__}, got {type(bid_task_data[field]).__name__}",
            }

    # Validate optional fields
    for field, expected_type in optional_fields.items():
        if field in bid_task_data and not isinstance(bid_task_data[field], expected_type):
            return {
                "success": False,
                "message": f"Invalid type for field '{field}': "
                           f"expected {expected_type.__name__}, got {type(bid_task_data[field]).__name__}",
            }

    try:
        # Create a BidTasksDB dataclass
        bid_task = BidTasksDB(
            bid_task_data=bid_task_data["bid_task_data"],
            bid_task_eval_dsl_id=bid_task_data.get("bid_task_eval_dsl_id", ""),
            bid_task_pqt_check_dsl_id=bid_task_data.get(
                "bid_task_pqt_check_dsl_id", ""),
            bid_task_post_evaluation_id=bid_task_data.get(
                "bid_task_post_evaluation_id", ""),
            bid_task_type=bid_task_data["bid_task_type"],
            bid_task_creator_subject=bid_task_data["bid_task_creator_subject"],
            bid_task_expiry_time=bid_task_data["bid_task_expiry_time"],
            bid_task_initiator_subject_id=bid_task_data["bid_task_initiator_subject_id"],
            bid_involved_subjects=bid_task_data.get(
                "bid_involved_subjects", []),
        )

        # Insert into the database
        db = BidTaskRegistryDB()
        if db.create_bid_task(bid_task):
            asyncio.run(_push_events(events_pusher, bid_task))
            return {"success": True, "data": bid_task.to_dict()}

        else:
            return {"success": False, "message": "Failed to create bid task in the database."}
    except Exception as e:
        return {"success": False, "message": f"An error occurred: {str(e)}"}


def check_pqt(bid_data: Bid, bid_task_data: BidTasksDB):
    try:

        if bid_task_data.bid_task_pqt_check_dsl_id == "":
            return True

        pqt_dsl_checker = new_dsl_workflow_executor(
            workflow_id=bid_task_data.bid_task_pqt_check_dsl_id,
            workflows_base_uri=os.getenv("DSL_DB_URL")
        )

        output = pqt_dsl_checker.execute({
            "bid_data": bid_data,
            "bid_task_data": bid_task_data.to_dict()
        })

        final_output = parse_dsl_output(output)
        if not final_output:
            raise Exception("pqt check failed, dsl did not emit any outputs")

        if 'allowed' in final_output and final_output['allowed']:
            return True

        raise Exception(final_output['reason_message'])

    except Exception as e:
        raise e


def submit_bid(bid_data: Dict) -> Dict:

    # Define required fields for the bid
    required_fields = ["bid_task_id", "bid_subject_id", "bid_data"]

    # Validate input fields
    missing_fields = [
        field for field in required_fields if field not in bid_data]
    if missing_fields:
        return {"success": False, "message": f"Missing required fields: {', '.join(missing_fields)}"}

    bid_task_id = bid_data["bid_task_id"]
    bid_subject_id = bid_data["bid_subject_id"]
    bid_info = bid_data["bid_data"]

    try:
        bid_task_db = BidTaskRegistryDB()
        bid_db = BidRegistryDB()

        # Check if the bid task exists
        bid_task = bid_task_db.get_bid_task(bid_task_id)
        if not bid_task:
            return {"success": False, "message": f"Bid task with ID '{bid_task_id}' does not exist."}

        # Check if the bid task is not expired
        if bid_task.is_expired():
            return {"success": False, "message": "Cannot submit bid; the bid task has expired."}

        # Check if the subject_id has already submitted a bid for the given bid_task_id
        existing_bids = bid_db.query_bids(
            {"bid_task_id": bid_task_id, "bid_subject_id": bid_subject_id})
        if existing_bids:
            return {"success": False, "message": "Subject has already submitted a bid for this bid task."}

        # Check if the bid_subject_id is allowed to participate
        if bid_task.bid_involved_subjects:
            if bid_subject_id not in bid_task.bid_involved_subjects:
                return {"success": False, "message": "Bid subject is not allowed to participate in this bid task."}

        # check PQT if specified:
        check_pqt(bid_data=bid_data, bid_task_data=bid_task)

        # Insert the bid into the database
        bid = Bid(
            bid_id="",
            bid_task_id=bid_task_id,
            creation_time=int(time.time()),
            bid_data=bid_info,
            bid_subject_id=bid_subject_id,
        )

        if bid_db.create_bid(bid):
            return {"success": True, "data": bid.to_dict()}
        else:
            return {"success": False, "message": "Failed to submit bid to the database."}
    except Exception as e:
        return {"success": False, "message": {str(e)}}
