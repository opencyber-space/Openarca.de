import logging
from .constraint import ConstraintWrapper, AsyncConstraintWrapper, ConstraintOutputWaiter

logging.basicConfig(level=logging.INFO)


class ConstraintsManager:
    def __init__(self):
        self._constraints = {}

    def load(self, message_type: str, subject_id: str, dsl_workflow_id: str):
        try:
            if message_type in self._constraints:
                logging.info(
                    f"Constraint for message type '{message_type}' is already loaded.")
                return

            logging.info(
                f"Loading constraint for message type '{message_type}'...")
            self._constraints[message_type] = ConstraintWrapper(
                message_type, subject_id, dsl_workflow_id)
            logging.info(
                f"Constraint for message type '{message_type}' loaded successfully.")
        except Exception as e:
            logging.error(
                f"Failed to load constraint for message type '{message_type}': {e}")
            raise

    def unload(self, message_type: str):
        try:
            if message_type not in self._constraints:
                logging.info(
                    f"Constraint for message type '{message_type}' is not loaded.")
                return

            logging.info(
                f"Unloading constraint for message type '{message_type}'...")
            self._constraints[message_type].clean_up()
            del self._constraints[message_type]
            logging.info(
                f"Constraint for message type '{message_type}' unloaded successfully.")
        except Exception as e:
            logging.error(
                f"Failed to unload constraint for message type '{message_type}': {e}")
            raise

    def check_constraint_and_convert_packet(self, message_type: str, input_data, subject_id: str, dsl_workflow_id: str):
        try:
            if message_type not in self._constraints:
                self.load(message_type, subject_id, dsl_workflow_id)

            logging.info(
                f"Executing constraint for message type '{message_type}'...")
            return self._constraints[message_type]._execute(input_data)
        except Exception as e:
            logging.error(
                f"Execution failed for message type '{message_type}': {e}")
            raise

    def get_metadata(self, message_type: str):
        try:
            if message_type not in self._constraints:
                raise ValueError(
                    f"Constraint for message type '{message_type}' is not loaded.")

            logging.info(
                f"Getting metadata for message type '{message_type}'...")
            return self._constraints[message_type].get_metadata()
        except Exception as e:
            logging.error(
                f"Failed to get metadata for message type '{message_type}': {e}")
            raise

    def clean_up(self, message_type: str):
        try:
            if message_type not in self._constraints:
                raise ValueError(
                    f"Constraint for message type '{message_type}' is not loaded.")

            logging.info(
                f"Cleaning up constraint for message type '{message_type}'...")
            self._constraints[message_type].clean_up()
        except Exception as e:
            logging.error(
                f"Failed to clean up for message type '{message_type}': {e}")
            raise


class AsyncConstraintsManager:
    def __init__(self):
        self._constraints = {}

    def load(self, message_type: str, subject_id: str, dsl_workflow_id: str):
        try:
            if message_type in self._constraints:
                logging.info(
                    f"Async constraint for message type '{message_type}' is already loaded.")
                return

            logging.info(
                f"Loading async constraint for message type '{message_type}'...")
            self._constraints[message_type] = AsyncConstraintWrapper(
                message_type, subject_id, dsl_workflow_id)
            logging.info(
                f"Async constraint for message type '{message_type}' loaded successfully.")
        except Exception as e:
            logging.error(
                f"Failed to load async constraint for message type '{message_type}': {e}")
            raise

    def unload(self, message_type: str):
        try:
            if message_type not in self._constraints:
                logging.info(
                    f"Async constraint for message type '{message_type}' is not loaded.")
                return

            logging.info(
                f"Unloading async constraint for message type '{message_type}'...")
            self._constraints[message_type].clean_up()
            del self._constraints[message_type]
            logging.info(
                f"Async constraint for message type '{message_type}' unloaded successfully.")
        except Exception as e:
            logging.error(
                f"Failed to unload async constraint for message type '{message_type}': {e}")
            raise

    def check_constraint_and_convert_packet(self, message_type: str, input_data, subject_id: str, dsl_workflow_id: str):
        try:
            if message_type not in self._constraints:
                self.load(message_type, subject_id, dsl_workflow_id)

            logging.info(
                f"Executing async constraint for message type '{message_type}'...")
            constraint = self._constraints[message_type]
            return constraint.add_task(input_data)
        except Exception as e:
            logging.error(
                f"Execution failed for message type '{message_type}': {e}")
            raise
