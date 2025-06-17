from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class SocialTaskCoreData:
    social_task_id: str
    created_by_subject_id: str
    created_by_subject_data: Dict
    org_ids: List[str]
    social_task_access_type: str  # private / public
    goal_data: Dict
    social_tasks_topics: List[str]
    social_task_properties: Dict
    creation_time: datetime
    scheduled_time: Optional[datetime] = None
    duration: Optional[int] = None
    status: Optional[str] = None
    report_json: Optional[Dict] = field(default_factory=dict)
    job_id: Optional[str] = None
    enable_live_streaming: Optional[bool] = False

    @staticmethod
    def from_dict(data: Dict) -> 'SocialTaskCoreData':
        return SocialTaskCoreData(**data)

    def to_dict(self) -> Dict:
        return self.__dict__


@dataclass
class SocialChoiceSubjectSpecInput:
    social_task_id: str
    topic_title: str
    topic_description: str
    voting_options_map: Dict
    voting_option_metadata_map: Dict
    supported_protocols: List[str]
    voting_message_request_creator_dsl: str

    @staticmethod
    def from_dict(data: Dict) -> 'SocialChoiceSubjectSpecInput':
        return SocialChoiceSubjectSpecInput(**data)

    def to_dict(self) -> Dict:
        return self.__dict__


@dataclass
class SocialChoiceEvaluationInput:
    social_task_id: str
    constraints_entry_id: str
    constraints_entry_id_1: str
    voting_pqt_dsl: str
    choice_evaluation_dsl: str
    tie_breaker_dsl: str
    post_awarding_dsl: str

    @staticmethod
    def from_dict(data: Dict) -> 'SocialChoiceEvaluationInput':
        return SocialChoiceEvaluationInput(**data)

    def to_dict(self) -> Dict:
        return self.__dict__


@dataclass
class Votes:
    vote_id: str
    social_task_id: str
    submitter_subject_id: str
    vote_data: Dict
    submission_time: datetime
    qualified: bool

    @staticmethod
    def from_dict(data: Dict) -> 'Votes':
        return Votes(**data)

    def to_dict(self) -> Dict:
        return self.__dict__
