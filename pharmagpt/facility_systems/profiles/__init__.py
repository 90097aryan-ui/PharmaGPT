"""
pharmagpt/facility_systems/profiles/__init__.py

Imports every profile module so their _register() calls execute, populating
FACILITY_SYSTEM_REGISTRY. Add a new module here to expose it automatically.
"""

from . import hvac_environmental  # HVAC, Environmental Monitoring System (EMS)
from . import utilities           # Purified Water, WFI, Clean Steam, Compressed Air,
                                   # Nitrogen, Vacuum, CIP, SIP
from . import controls_electrical # BMS, Electrical Distribution, Fire Alarm, Access Control


def _autoload():
    """No-op — importing this package is sufficient to trigger all registrations."""
