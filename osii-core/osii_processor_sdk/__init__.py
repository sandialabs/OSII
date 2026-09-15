"""Compatibility imports for processors written before SDK consolidation.

New code should import from ``osii.processor_sdk``. Both namespaces expose the
same classes and modules so existing processors remain compatible.
"""

import sys

from osii.processor_sdk import *  # noqa: F403
from osii.processor_sdk import __all__, client, models, service

sys.modules[__name__ + ".client"] = client
sys.modules[__name__ + ".models"] = models
sys.modules[__name__ + ".service"] = service
