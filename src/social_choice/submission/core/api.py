from flask import Flask, request, jsonify
import logging
from .submission import SocialTaskController, SubmissionParser, SubmissionValidationError
from .votes_request import start_voting_tasks_scheduler

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SocialChoiceTaskAPI")

# Instantiate the controller (you can inject config if needed)
task_controller = SocialTaskController()


@app.route("/submit-social-choice-task", methods=["POST"])
def submit_social_choice_task():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Empty or invalid JSON payload"}), 400

        social_task_id = task_controller.create_social_choice_task(payload)
        return jsonify({"social_task_id": social_task_id}), 201

    except SubmissionValidationError as ve:
        logger.warning(f"Validation error: {str(ve)}")
        return jsonify({"error": str(ve)}), 400

    except Exception as e:
        logger.exception("Unexpected error during task submission")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/parse-social-choice-task", methods=["POST"])
def parse_social_choice_task():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Empty or invalid JSON payload"}), 400

        task, subject_spec, evaluation = SubmissionParser.validate_and_parse(
            payload)

        return jsonify({
            "parsed": {
                "social_task": task.to_dict(),
                "subject_spec": subject_spec.to_dict(),
                "evaluation_spec": evaluation.to_dict()
            }
        }), 200

    except SubmissionValidationError as ve:
        logger.warning(f"Validation error: {str(ve)}")
        return jsonify({"error": str(ve)}), 400

    except Exception as e:
        logger.exception("Unexpected error during parsing")
        return jsonify({"error": "Internal server error"}), 500


def run_server():
    start_voting_tasks_scheduler()
    app.run(host='0.0.0.0', port=5000)