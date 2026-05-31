from typing import Annotated

from fastapi import Depends, Request

from autoresearch_api.db.resources import AppResources
from autoresearch_api.db.repositories import Repositories


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources


def get_repositories(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> Repositories:
    return resources.repositories
