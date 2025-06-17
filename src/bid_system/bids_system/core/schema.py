from dataclasses import dataclass, field
from typing import List, Dict
import uuid
import time


@dataclass
class BidTasksDB:
    bid_task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bid_task_data: Dict = field(default_factory=dict)
    bid_task_eval_dsl_id: str = ""
    bid_task_pqt_check_dsl_id: str = ""
    bid_task_post_evaluation_id: str = ""
    bid_task_type: str = ""
    bid_task_creator_subject: str = ""
    bid_task_expiry_time: int = field(
        default_factory=lambda: int(time.time()) + 86400)
    bid_task_initiator_subject_id: str = ""
    bid_involved_subjects: List[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        current_time = int(time.time())
        return current_time > self.bid_task_expiry_time

    def add_involved_subject(self, subject: str):
        if subject not in self.bid_involved_subjects:
            self.bid_involved_subjects.append(subject)

    def to_dict(self) -> Dict:

        return {
            "bid_task_id": self.bid_task_id,
            "bid_task_data": self.bid_task_data,
            "bid_task_eval_dsl_id": self.bid_task_eval_dsl_id,
            "bid_task_pqt_check_dsl_id": self.bid_task_pqt_check_dsl_id,
            "bid_task_post_evaluation_id": self.bid_task_post_evaluation_id,
            "bid_task_type": self.bid_task_type,
            "bid_task_creator_subject": self.bid_task_creator_subject,
            "bid_task_expiry_time": self.bid_task_expiry_time,
            "bid_task_initiator_subject_id": self.bid_task_initiator_subject_id,
            "bid_involved_subjects": self.bid_involved_subjects,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            bid_task_id=data.get("bid_task_id", str(uuid.uuid4())),
            bid_task_data=data.get("bid_task_data", {}),
            bid_task_eval_dsl_id=data.get("bid_task_eval_dsl_id", ""),
            bid_task_pqt_check_dsl_id=data.get(
                "bid_task_pqt_check_dsl_id", ""),
            bid_task_post_evaluation_id=data.get(
                "bid_task_post_evaluation_id", ""),
            bid_task_type=data.get("bid_task_type", ""),
            bid_task_creator_subject=data.get("bid_task_creator_subject", ""),
            bid_task_expiry_time=data.get(
                "bid_task_expiry_time", int(time.time()) + 86400),
            bid_task_initiator_subject_id=data.get(
                "bid_task_initiator_subject_id", ""),
            bid_involved_subjects=data.get("bid_involved_subjects", []),
        )


@dataclass
class Bid:
    bid_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bid_task_id: str = ""
    creation_time: int = field(default_factory=lambda: int(time.time()))
    bid_data: Dict = field(default_factory=dict)
    bid_subject_id: str = ""

    def to_dict(self) -> Dict:
        return {
            "bid_id": self.bid_id,
            "bid_task_id": self.bid_task_id,
            "creation_time": self.creation_time,
            "bid_data": self.bid_data,
            "bid_subject_id": self.bid_subject_id,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            bid_id=data.get("bid_id", str(uuid.uuid4())),
            bid_task_id=data.get("bid_task_id", ""),
            creation_time=data.get("creation_time", int(time.time())),
            bid_data=data.get("bid_data", {}),
            bid_subject_id=data.get("bid_subject_id", ""),
        )


@dataclass
class BidTaskResults:
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bid_task_id: str = ""
    bid_task_data: Dict = field(default_factory=dict)
    winner_subject_ids: List[str] = field(default_factory=list)
    eval_result_data: Dict = field(default_factory=dict)
    initiated_by: str = ""
    bid_task_type: str = ""
    created_at: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> Dict:
        return {
            "result_id": self.result_id,
            "bid_task_id": self.bid_task_id,
            "bid_task_data": self.bid_task_data,
            "winner_subject_ids": self.winner_subject_ids,
            "eval_result_data": self.eval_result_data,
            "initiated_by": self.initiated_by,
            "bid_task_type": self.bid_task_type,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            result_id=data.get("result_id", str(uuid.uuid4())),
            bid_task_id=data.get("bid_task_id", ""),
            bid_task_data=data.get("bid_task_data", {}),
            winner_subject_ids=data.get("winner_subject_ids", []),
            eval_result_data=data.get("eval_result_data", {}),
            initiated_by=data.get("initiated_by", ""),
            bid_task_type=data.get("bid_task_type", ""),
            created_at=data.get("created_at", int(time.time())),
        )
