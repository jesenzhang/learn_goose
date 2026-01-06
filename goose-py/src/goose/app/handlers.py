from goose.command.bus import ICommandHandler
from goose.app.commands import RunWorkflowCommand
from goose.app.execution_service import ExecutionService

class RunWorkflowHandler(ICommandHandler[str]):
    def __init__(self, service: ExecutionService):
        self.service = service

    async def handle(self, command: RunWorkflowCommand) -> str:
        # 实际调用 Service
        return await self.service.run_workflow(
            wf_id=command.workflow_id,
            inputs=command.inputs,
            user_id=command.user_id
        )