from typing import Annotated

from fastapi import Depends, Request

from autoresearch_api.db.repositories import Repositories
from autoresearch_api.db.resources import AppResources
from autoresearch_api.programs.service import ProgramService
from autoresearch_api.tools.service import ToolService


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources


def get_repositories(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> Repositories:
    return resources.repositories


def get_program_service(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> ProgramService:
    return ProgramService(resources.postgres)


def get_tool_service(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> ToolService:
    return ToolService(resources.postgres, resources.neo4j)
