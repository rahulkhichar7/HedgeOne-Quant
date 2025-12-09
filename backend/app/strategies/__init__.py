import pkgutil
import inspect
from typing import Dict, Type
from .base import BaseStrategy

# Dictionary to hold the strategy class instances, mapped by their ID
STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}

# --- Auto-Discovery Logic ---
for loader, name, is_pkg in pkgutil.walk_packages(__path__):
    if not is_pkg and name != 'base': 
        try:
            # Import the module dynamically
            module = loader.find_module(name).load_module(name)
            
            # Look for classes inheriting from BaseStrategy
            for item_name, item_obj in inspect.getmembers(module):
                if inspect.isclass(item_obj):
                    if issubclass(item_obj, BaseStrategy) and item_obj is not BaseStrategy:
                        # Register the strategy using its defined strategy_id
                        STRATEGY_REGISTRY[item_obj.strategy_id] = item_obj
                        
        except Exception as e:
            # Print error but continue loading other strategies
            print(f"Error loading strategy module {name}: {e}")

# The line `from ..strategies import registry` in vectorbt_engine.py 
# implicitly imports this STRATEGY_REGISTRY as the module's attribute.
# For clarity, we define an alias used by VBT Engine:
registry = STRATEGY_REGISTRY