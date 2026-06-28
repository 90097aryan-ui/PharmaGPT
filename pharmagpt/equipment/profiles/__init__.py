"""
pharmagpt/equipment/profiles/__init__.py

Imports every profile module so their _register() calls execute, populating
EQUIPMENT_REGISTRY. Add a new module here to expose it automatically.
"""

from . import analytical       # HPLC, GC, UV Spectrophotometer
from . import testing          # Dissolution Tester, Friability Tester, Hardness Tester
from . import sterilization    # Autoclave, VHP Generator
from . import manufacturing    # Tablet Compression Machine, Capsule Filling Machine
from . import packaging        # Blister Packing, Bottle Filling, Cartoner, Labeler
from . import quality_control  # Checkweigher, Metal Detector
from . import processing       # Tablet Coater, Fluid Bed Dryer, RMG, Bin Blender


def _autoload():
    """No-op — importing this package is sufficient to trigger all registrations."""
