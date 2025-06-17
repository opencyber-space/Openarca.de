from core.initiator import Initiator
from core.dsl_flow_executor import DSLEvaluator
from core.finalizer import VoteResultFinalizer
from core.finalizer import ResultNotifier
import asyncio

if __name__ == "__main__":
    initiator = Initiator()
    task, subject_spec, evaluation_spec, votes = initiator.load()

    evaluator = DSLEvaluator()
    result = evaluator.evaluate(task, subject_spec, evaluation_spec, votes)

    winners = result["winners"]
    post_payload = result["post_award_payload"]
    dsl_outputs = result["dsl_outputs"]

    finalizer = VoteResultFinalizer()
    report = finalizer.finalize(task, subject_spec, evaluation_spec, votes, winners, post_payload, dsl_outputs)

    notifier = ResultNotifier()
    asyncio.run(notifier.notify(winners, task.social_task_id, post_payload))
