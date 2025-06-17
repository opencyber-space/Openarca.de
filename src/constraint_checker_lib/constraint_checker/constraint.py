import os
from multiprocessing import Process, Queue
import logging

from .dsl_executor import new_dsl_workflow_executor, parse_dsl_output
from .dsl_executor.workflow_executor import DSLWorkflowExecutor


class ConstraintWrapper:

    def __init__(self, message_type: str, subject_id: str, dsl_workflow_id: str) -> None:
        self.message_type = message_type
        self.subject_id = subject_id
        self.dsl_workflow_id = dsl_workflow_id
        self.dsl = self._load_constraint_dsl(self.dsl_workflow_id)

    def _load_constraint_dsl(self, dsl_workflow_id):
        try:

            # TODO: connect with the subject's DB, for now DSL is passed through parameter
            dsl = new_dsl_workflow_executor(
                dsl_workflow_id, os.getenv("DSL_DB_URL"))
            return dsl

        except Exception as e:
            raise e

    def _execute(self, input_data):
        try:

            output = self.dsl.execute(input_data)
            return parse_dsl_output(output, "")

        except Exception as e:
            raise e

    def get_metadata(self):
        return {
            "settings": self.dsl.global_settings,
            "parameters": self.dsl.global_parameters,
            "modules": self.dsl.modules
        }

    def clean_up(self):
        try:
            self.dsl.clean_up()
        except Exception as e:
            raise e


class ConstraintOutputWaiter:
    def __init__(self, output_queue: Queue):
        self._output_queue = output_queue

    def wait(self):
        return self._output_queue.get()


class AsyncConstraintWrapper:
    def __init__(self, message_type: str, subject_id: str, dsl_workflow_id: str):
        self.message_type = message_type
        self.subject_id = subject_id
        self.dsl_workflow_id = dsl_workflow_id
        self.input_queue = Queue()
        self.process = Process(target=self._run_dsl_process)
        self.process.start()

    def _run_dsl_process(self):

        try:
            from .dsl_executor import new_dsl_workflow_executor, parse_dsl_output

            dsl = new_dsl_workflow_executor(
                self.dsl_workflow_id, os.getenv("DSL_DB_URL"))
            while True:
                input_data, output_queue = self.input_queue.get()
                try:
                    output = dsl.execute(input_data)
                    parsed_output = parse_dsl_output(output, "")
                    output_queue.put(parsed_output)
                except Exception as e:
                    output_queue.put(e)
        except Exception as e:
            logging.error(
                f"DSL process for message type '{self.message_type}' encountered an error: {e}")

    def add_task(self, input_data):
        output_queue = Queue(maxsize=1)
        self.input_queue.put((input_data, output_queue))
        return ConstraintOutputWaiter(output_queue)

    def clean_up(self):
        self.process.terminate()
        self.process.join()
