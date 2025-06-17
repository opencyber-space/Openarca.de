from .constraints_manager import AsyncConstraintsManager, ConstraintsManager
from .constraint import ConstraintOutputWaiter


def new_constraints_manager():
    return ConstraintsManager()

def new_async_constraints_manager():
    return AsyncConstraintsManager()