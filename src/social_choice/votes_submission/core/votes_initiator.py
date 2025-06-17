import os
import logging
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .basic_crud import SocialTaskCoreDataDB, VotesDB

logger = logging.getLogger("VotingEvaluationInitiator")
logging.basicConfig(level=logging.INFO)


class VotingEvaluationInitiator:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.votes_db = VotesDB(mongo_uri, db_name)

        # Load in-cluster Kubernetes configuration
        try:
            config.load_incluster_config()
            self.batch_v1 = client.BatchV1Api()
            self.core_v1 = client.CoreV1Api()
        except Exception as e:
            logger.exception("Failed to load Kubernetes in-cluster config")
            raise e

    def should_initiate_evaluation(self, social_task_id: str) -> bool:
        task = self.task_db.get(social_task_id)
        if not task:
            logger.error(f"Task not found: {social_task_id}")
            return False

        votes = self.votes_db.list_by_task(social_task_id)
        qualified_votes = [v for v in votes if v.qualified]

        if task.social_task_access_type == "private":
            expected_voters = set(task.org_ids)
            received_voters = set(v.submitter_subject_id for v in qualified_votes)
            if expected_voters.issubset(received_voters):
                logger.info(f"All private voters submitted votes for {social_task_id}")
                return True
            else:
                logger.info(f"Private task {social_task_id} waiting for more votes.")
                return False

        elif task.social_task_access_type == "public":
            required_votes = task.duration or 5  # Use duration as threshold fallback
            if len(qualified_votes) >= required_votes:
                logger.info(f"Public task {social_task_id} met threshold with {len(qualified_votes)} votes.")
                return True
            else:
                logger.info(f"Public task {social_task_id} needs more votes ({len(qualified_votes)}/{required_votes})")
                return False

        return False

    def ensure_namespace_exists(self, namespace: str):
        try:
            self.core_v1.read_namespace(name=namespace)
            logger.info(f"Namespace '{namespace}' already exists.")
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Namespace '{namespace}' not found. Creating...")
                ns_body = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=namespace)
                )
                self.core_v1.create_namespace(ns_body)
                logger.info(f"Namespace '{namespace}' created successfully.")
            else:
                logger.exception("Failed to check/create namespace.")
                raise

    def launch_evaluation_job(self, social_task_id: str):
        if not self.should_initiate_evaluation(social_task_id):
            return

        namespace = "votes-evaluation"
        job_name = social_task_id

        self.ensure_namespace_exists(namespace)

        envs = [
            client.V1EnvVar(name="SOCIAL_TASK_ID", value=social_task_id),
            client.V1EnvVar(name="MONGO_URL", value=os.getenv("MONGO_URL", "mongodb://localhost:27017")),
            client.V1EnvVar(name="ORG_NATS_URL", value=os.getenv("ORG_NATS_URL", "nats://localhost:4222"))
        ]

        container = client.V1Container(
            name="votes-evaluator",
            image="agentspacev1/votes-evaluator:v1",
            env=envs
        )

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"job": job_name}),
            spec=client.V1PodSpec(restart_policy="Never", containers=[container])
        )

        job_spec = client.V1JobSpec(template=template, backoff_limit=0)

        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name),
            spec=job_spec
        )

        try:
            logger.info(f"Creating job for task {social_task_id} in namespace '{namespace}'")
            self.batch_v1.create_namespaced_job(namespace=namespace, body=job)
            logger.info(f"Job '{job_name}' created.")
        except ApiException as e:
            if e.status == 409:
                logger.warning(f"Job '{job_name}' already exists.")
            else:
                logger.exception(f"Failed to create job for task {social_task_id}")
                raise
