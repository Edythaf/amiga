"""Compatibility imports. Primary queue implementation lives in the supplied backend module."""
from .modules.upload.queue_worker import claim, process_one, start_worker, real_extractor
