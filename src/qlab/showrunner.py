"""Qlab - A ShowRunner plugin."""

from fastapi import APIRouter

import showrunner

router = APIRouter(prefix="/qlab", tags=["Qlab"])


@router.get("/")
async def index():
    return {"plugin": "Qlab", "status": "ok"}


class Qlab:
    """A ShowRunner plugin."""

    @showrunner.hookimpl
    def showrunner_register(self):
        return {
            "name": "Qlab",
            "description": "A ShowRunner plugin.",
            "version": "0.1.0",
        }

    @showrunner.hookimpl
    def showrunner_startup(self, app):
        pass

    @showrunner.hookimpl
    def showrunner_shutdown(self, app):
        pass

    @showrunner.hookimpl
    def showrunner_get_routes(self):
        return router

    @showrunner.hookimpl
    def showrunner_get_commands(self):
        return []

    @showrunner.hookimpl
    def showrunner_get_nav(self):
        return None

    @showrunner.hookimpl
    def showrunner_get_status(self):
        return None


plugin = Qlab()
