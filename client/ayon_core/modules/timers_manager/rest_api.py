import json

from aiohttp.web_response import Response
from ayon_core.lib import Logger


class TimersManagerAddonRestApi:
    """
        REST API endpoint used for calling from hosts when context change
        happens in Workfile app.
    """
    def __init__(self, user_addon, server_manager):
        self._log = None
        self._addon = user_addon
        self._server_manager = server_manager

        self._prefix = "/timers_manager"

        self.register()

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    def register(self):
        self._server_manager.add_route(
            "POST",
            self._prefix + "/start_timer",
            self.start_timer
        )
        self._server_manager.add_route(
            "POST",
            self._prefix + "/stop_timer",
            self.stop_timer
        )
        self._server_manager.add_route(
            "GET",
            self._prefix + "/get_task_time",
            self.get_task_time
        )

    async def start_timer(self, request):
        data = await request.json()
        try:
            project_name = data["project_name"]
            asset_name = data["asset_name"]
            task_name = data["task_name"]
        except KeyError:
            msg = (
                "Payload must contain fields 'project_name,"
                " 'asset_name' and 'task_name'"
            )
            self.log.error(msg)
            return Response(status=400, message=msg)

        self._addon.stop_timers()
        try:
            self._addon.start_timer(project_name, asset_name, task_name)
        except Exception as exc:
            return Response(status=404, message=str(exc))

        return Response(status=200)

    async def stop_timer(self, request):
        self._addon.stop_timers()
        return Response(status=200)

    async def get_task_time(self, request):
        data = await request.json()
        try:
            project_name = data['project_name']
            asset_name = data['asset_name']
            task_name = data['task_name']
        except KeyError:
            message = (
                "Payload must contain fields 'project_name, 'asset_name',"
                " 'task_name'"
            )
            self.log.warning(message)
            return Response(text=message, status=404)

        time = self._addon.get_task_time(project_name, asset_name, task_name)
        return Response(text=json.dumps(time))
