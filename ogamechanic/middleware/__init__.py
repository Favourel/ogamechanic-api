"""
Middleware package for OGAMechanic platform.
"""

from .audit_middleware import StrategicAuditMiddleware

__all__ = ['StrategicAuditMiddleware']
