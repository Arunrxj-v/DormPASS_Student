"""API v1 routers."""

from .admin import router as admin_router
from .attendance import router as attendance_router
from .auth import router as auth_router
from .config import router as config_router
from .face_enrollment import router as face_enrollment_router
from .health import router as health_router
from .hostels import router as hostels_router
from .students import router as students_router
from .warden import router as warden_router

__all__ = [
    "admin_router",
    "attendance_router",
    "auth_router",
    "config_router",
    "face_enrollment_router",
    "health_router",
    "hostels_router",
    "students_router",
    "warden_router",
]
