from pymongo import MongoClient
from typing import Optional, List
from datetime import datetime
from .schema import *


class SocialTaskCoreDataDB:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.client = MongoClient(mongo_uri)
        self.collection = self.client[db_name]["social_task_core_data"]

    def create(self, task: SocialTaskCoreData):
        self.collection.insert_one(task.to_dict())

    def get(self, social_task_id: str) -> Optional[SocialTaskCoreData]:
        data = self.collection.find_one({"social_task_id": social_task_id})
        return SocialTaskCoreData.from_dict(data) if data else None

    def update(self, social_task_id: str, updates: dict):
        self.collection.update_one(
            {"social_task_id": social_task_id}, {"$set": updates})

    def delete(self, social_task_id: str):
        self.collection.delete_one({"social_task_id": social_task_id})

    def list_all(self) -> List[SocialTaskCoreData]:
        return [SocialTaskCoreData.from_dict(d) for d in self.collection.find()]


class SocialChoiceSubjectSpecInputDB:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.client = MongoClient(mongo_uri)
        self.collection = self.client[db_name]["social_choice_subject_spec"]

    def create(self, entry: SocialChoiceSubjectSpecInput):
        self.collection.insert_one(entry.to_dict())

    def get(self, social_task_id: str) -> Optional[SocialChoiceSubjectSpecInput]:
        data = self.collection.find_one({"social_task_id": social_task_id})
        return SocialChoiceSubjectSpecInput.from_dict(data) if data else None

    def update(self, social_task_id: str, updates: dict):
        self.collection.update_one(
            {"social_task_id": social_task_id}, {"$set": updates})

    def delete(self, social_task_id: str):
        self.collection.delete_one({"social_task_id": social_task_id})

    def list_all(self) -> List[SocialChoiceSubjectSpecInput]:
        return [SocialChoiceSubjectSpecInput.from_dict(d) for d in self.collection.find()]


class SocialChoiceEvaluationInputDB:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.client = MongoClient(mongo_uri)
        self.collection = self.client[db_name]["social_choice_evaluation_input"]

    def create(self, entry: SocialChoiceEvaluationInput):
        self.collection.insert_one(entry.to_dict())

    def get(self, social_task_id: str) -> Optional[SocialChoiceEvaluationInput]:
        data = self.collection.find_one({"social_task_id": social_task_id})
        return SocialChoiceEvaluationInput.from_dict(data) if data else None

    def update(self, social_task_id: str, updates: dict):
        self.collection.update_one(
            {"social_task_id": social_task_id}, {"$set": updates})

    def delete(self, social_task_id: str):
        self.collection.delete_one({"social_task_id": social_task_id})

    def list_all(self) -> List[SocialChoiceEvaluationInput]:
        return [SocialChoiceEvaluationInput.from_dict(d) for d in self.collection.find()]


class VotesDB:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.client = MongoClient(mongo_uri)
        self.collection = self.client[db_name]["votes"]

    def create(self, vote: Votes):
        self.collection.insert_one(vote.to_dict())

    def get(self, vote_id: str) -> Optional[Votes]:
        data = self.collection.find_one({"vote_id": vote_id})
        return Votes.from_dict(data) if data else None

    def update(self, vote_id: str, updates: dict):
        self.collection.update_one({"vote_id": vote_id}, {"$set": updates})

    def delete(self, vote_id: str):
        self.collection.delete_one({"vote_id": vote_id})

    def list_by_task(self, social_task_id: str) -> List[Votes]:
        return [Votes.from_dict(d) for d in self.collection.find({"social_task_id": social_task_id})]

    def list_all(self) -> List[Votes]:
        return [Votes.from_dict(d) for d in self.collection.find()]
