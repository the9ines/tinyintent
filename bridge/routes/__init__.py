"""
TinyIntent Bridge Routes Package

Modular route organization for better maintainability.
"""

from .health import health_router
from .helpers import helpers_router  
from .agents import agents_router
from .shortcut import shortcut_router
from .system import system_router

__all__ = [
    'health_router',
    'helpers_router', 
    'agents_router',
    'shortcut_router',
    'system_router'
]