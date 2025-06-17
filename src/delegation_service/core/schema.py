import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DelegationStatus:
    state: str = ""
    time: int = field(default_factory=lambda: int(
        time.time()))  # Timestamp in seconds
    deadline: Optional[int] = None  # Optional deadline in seconds
    delegation_result: Optional[str] = None  # Result of the delegation

    def to_dict(self) -> Dict:
        return {
            "state": self.state,
            "time": self.time,
            "deadline": self.deadline,
            "delegation_result": self.delegation_result,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            state=data.get("state", ""),
            time=data.get("time", int(time.time())),
            deadline=data.get("deadline"),
            delegation_result=data.get("delegation_result"),
        )


@dataclass
class Delegation:
    delegation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    sub_task_id: str = ""
    workflow_level: int = 0
    delegation_type: str = ""
    target_subject_id: str = ""
    sender_subject_id: str = ""
    status: Dict[str, DelegationStatus] = field(default_factory=dict)
    sub_task_data: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "delegation_id": self.delegation_id,
            "task_id": self.task_id,
            "sub_task_id": self.sub_task_id,
            "sub_task_data": self.sub_task_data,
            "workflow_level": self.workflow_level,
            "delegation_type": self.delegation_type,
            "target_subject_id": self.target_subject_id,
            "sender_subject_id": self.sender_subject_id,
            "status": {k: v.to_dict() for k, v in self.status.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            delegation_id=data.get("delegation_id", str(uuid.uuid4())),
            task_id=data.get("task_id", ""),
            sub_task_id=data.get("sub_task_id", ""),
            sub_task_data=data.get("sub_task_data", {}),
            workflow_level=data.get("workflow_level", 0),
            delegation_type=data.get("delegation_type", ""),
            target_subject_id=data.get("target_subject_id", ""),
            status={k: DelegationStatus.from_dict(
                v) for k, v in data.get("status", {}).items()},
            sender_subject_id=data.get("sender_subject_id", "")
        )
