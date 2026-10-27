"""Compatibility import; primary controllers live in the supplied module layout."""
from .api_common import api, authenticate
from .modules.auth import routes as _auth_routes
from .modules.auth import password_routes as _password_routes
from .modules.admin import routes as _admin_routes
from .modules.upload import routes as _upload_routes
from .modules.agents import routes as _agent_routes
from .modules.telegram import routes as _telegram_routes

from .modules.upload import manual_routes as _manual_routes
from .modules.upload import batch_routes as _batch_routes
from .modules.upload import tax_routes as _tax_routes
