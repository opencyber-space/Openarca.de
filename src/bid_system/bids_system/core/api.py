import threading
from flask import Flask, request, jsonify
from .db import BidTaskRegistryDB, BidRegistryDB, BidTaskResultsRegistry
from .evaluator import BidsEvaluator
from .submissions import submit_bid, create_bidding_task

app = Flask(__name__)

bid_task_db = BidTaskRegistryDB()
bid_db = BidRegistryDB()
results_registry = BidTaskResultsRegistry()


# Helper function to format responses
def response(success, data=None, message=None):
    if success:
        return jsonify({"success": True, "data": data})
    else:
        return jsonify({"success": False, "message": message})


# BidTaskRegistryDB APIs
@app.route('/bid-tasks/<string:bid_task_id>', methods=['GET'])
def get_bid_task(bid_task_id):
    try:
        bid_task = bid_task_db.get_bid_task(bid_task_id)
        if bid_task:
            return response(True, bid_task.to_dict())
        return response(False, message="Bid task not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bid-tasks/<string:bid_task_id>', methods=['PUT'])
def update_bid_task(bid_task_id):
    try:
        updated_data = request.json
        if bid_task_db.update_bid_task(bid_task_id, updated_data):
            return response(True, data="Bid task updated successfully")
        return response(False, message="Bid task not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bid-tasks/<string:bid_task_id>', methods=['DELETE'])
def delete_bid_task(bid_task_id):
    try:
        if bid_task_db.delete_bid_task(bid_task_id):
            return response(True, data="Bid task deleted successfully")
        return response(False, message="Bid task not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bid-tasks', methods=['GET'])
def list_bid_tasks():
    try:
        bid_tasks = bid_task_db.list_bid_tasks()
        return response(True, [task.to_dict() for task in bid_tasks])
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bid-tasks/query', methods=['POST'])
def query_bid_tasks():
    try:
        query = request.json
        bid_tasks = bid_task_db.query_bid_tasks(query)
        return response(True, [task.to_dict() for task in bid_tasks])
    except Exception as e:
        return response(False, message=str(e))


# BidRegistryDB APIs
@app.route('/bids/<string:bid_id>', methods=['GET'])
def get_bid(bid_id):
    try:
        bid = bid_db.get_bid(bid_id)
        if bid:
            return response(True, bid.to_dict())
        return response(False, message="Bid not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bids/<string:bid_id>', methods=['PUT'])
def update_bid(bid_id):
    try:
        updated_data = request.json
        if bid_db.update_bid(bid_id, updated_data):
            return response(True, data="Bid updated successfully")
        return response(False, message="Bid not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bids/<string:bid_id>', methods=['DELETE'])
def delete_bid(bid_id):
    try:
        if bid_db.delete_bid(bid_id):
            return response(True, data="Bid deleted successfully")
        return response(False, message="Bid not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bids', methods=['GET'])
def list_bids():
    try:
        bids = bid_db.list_bids()
        return response(True, [bid.to_dict() for bid in bids])
    except Exception as e:
        return response(False, message=str(e))


@app.route('/bids/query', methods=['POST'])
def query_bids():
    try:
        query = request.json
        bids = bid_db.query_bids(query)
        return response(True, [bid.to_dict() for bid in bids])
    except Exception as e:
        return response(False, message=str(e))


@app.route("/bid-task-results/<result_id>", methods=["GET"])
def get_result(result_id):
    try:
        result = results_registry.get_result(result_id)
        if not result:
            return jsonify({"success": False, "message": "Result not found"}), 404
        return jsonify({"success": True, "data": result.to_dict()}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/bid-task-results", methods=["GET"])
def query_results():
    try:
        query = request.json or {}
        results = results_registry.query_results(query)
        return jsonify({"success": True, "data": [result.to_dict() for result in results]}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/bid-task-results/<result_id>", methods=["PUT"])
def update_result(result_id):
    try:
        update_data = request.json or {}
        updated = results_registry.update_result(result_id, update_data)
        if not updated:
            return jsonify({"success": False, "message": "Result not found or not updated"}), 404
        return jsonify({"success": True, "message": "Result updated"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/bid-task-results/<result_id>", methods=["DELETE"])
def delete_result(result_id):
    try:
        deleted = results_registry.delete_result(result_id)
        if not deleted:
            return jsonify({"success": False, "message": "Result not found"}), 404
        return jsonify({"success": True, "message": "Result deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/bid-task/submit-task", methods=['POST'])
def submit_bid_task():
    try:

        data = request.get_json()

        response = create_bidding_task(data)

        return response, 200
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/bids/submit-bid", methods=['POST'])
def submit_bid_entry():
    try:

        data = request.get_json()

        response = submit_bid(data)

        return response, 200
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/bid-task/<bid_task_id>/start-evaluation", methods=["POST"])
def start_evaluation(bid_task_id):
    try:
        def evaluate_task():
            evaluator = BidsEvaluator(bid_task_id)
            evaluator.evaluate()

        thread = threading.Thread(target=evaluate_task)
        thread.start()

        return jsonify({"success": True, "message": f"Evaluation for BidTask {bid_task_id} has started in the background."}), 202

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

def run_app():
    app.run(host='0.0.0.0', port=5000)
