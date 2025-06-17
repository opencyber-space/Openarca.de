import os
import logging
from flask import Flask, jsonify, request
from .db import DelegationRegistry, Delegation

app = Flask(__name__)
delegation_registry = DelegationRegistry()


def response(success, data=None, message=None):
    if success:
        return jsonify({"success": True, "data": data})
    else:
        return jsonify({"success": False, "message": message})

# Delegation APIs


@app.route('/delegations/<string:delegation_id>', methods=['GET'])
def get_delegation(delegation_id):
    try:
        delegation = delegation_registry.get_delegation(delegation_id)
        if delegation:
            return response(True, delegation.to_dict())
        return response(False, message="Delegation not found")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/delegations', methods=['POST'])
def create_delegation():
    try:
        data = request.json
        delegation = Delegation.from_dict(data)
        success = delegation_registry.create_delegation(delegation)
        if success:
            return response(True, message="Delegation created successfully")
        return response(False, message="Failed to create delegation")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/delegations/<string:delegation_id>', methods=['PUT'])
def update_delegation(delegation_id):
    try:
        update_data = request.json
        success = delegation_registry.update_delegation(
            delegation_id, update_data)
        if success:
            return response(True, message="Delegation updated successfully")
        return response(False, message="Failed to update delegation")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/delegations/<string:delegation_id>', methods=['DELETE'])
def delete_delegation(delegation_id):
    try:
        success = delegation_registry.delete_delegation(delegation_id)
        if success:
            return response(True, message="Delegation deleted successfully")
        return response(False, message="Failed to delete delegation")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/delegations/query', methods=['POST'])
def query_delegations():
    try:
        query = request.json
        delegations = delegation_registry.query_delegations(query)
        return response(True, [delegation.to_dict() for delegation in delegations])
    except Exception as e:
        return response(False, message=str(e))


@app.route('/delegations/<string:delegation_id>/status/<string:status_key>', methods=['PUT'])
def update_delegation_status(delegation_id, status_key):
    try:
        status_data = request.json
        success = delegation_registry.update_status(
            delegation_id, status_key, status_data)
        if success:
            return response(True, message="Delegation status updated successfully")
        return response(False, message="Failed to update delegation status")
    except Exception as e:
        return response(False, message=str(e))


@app.route('/delegations/submit_result/<string:delegation_id>', methods=['PUT'])
def submit_delegation_result(delegation_id):
    try:
        status_data = request.json
        success = delegation_registry.update_status(
            delegation_id, "delegation_result", status_data)
        if success:
            return response(True, message="Delegation status updated successfully")
        return response(False, message="Failed to update delegation status")
    except Exception as e:
        return response(False, message=str(e))


def run_server():
    app.run(debug=True)
