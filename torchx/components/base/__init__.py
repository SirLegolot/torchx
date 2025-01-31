# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
These components are meant to be used as convenience methods when constructing
other components. Many methods in the base component library are factory methods
for ``Role``, ``Container``, and ``Resources`` that are hooked up to
TorchX's configurable extension points.
"""
from typing import Any, Dict, List, Optional, Union

from torchx.specs import named_resources
from torchx.specs.api import NULL_RESOURCE, Resource, RetryPolicy, Role
from torchx.util.entrypoints import load

from .roles import create_torch_dist_role


def _resolve_resource(resource: Union[str, Resource]) -> Resource:
    if isinstance(resource, Resource):
        return resource
    else:
        return named_resources[resource.upper()]


def torch_dist_role(
    name: str,
    image: str,
    entrypoint: str,
    resource: Union[str, Resource] = NULL_RESOURCE,
    base_image: Optional[str] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    num_replicas: int = 1,
    max_retries: int = 0,
    port_map: Optional[Dict[str, int]] = None,
    retry_policy: RetryPolicy = RetryPolicy.APPLICATION,
    **launch_kwargs: Any,
) -> Role:
    """
    A ``Role`` for which the user provided ``entrypoint`` is executed with the
        torchelastic agent (in the container). Note that the torchelastic agent
        invokes multiple copies of ``entrypoint``.

    The method will try to search factory method that is registered via entrypoints.
    If no group or role found, the default ``torchx.components.base.role.create_torch_dist_role``
    will be used.

    For more information see ``torchx.components.base.roles``

    Usage:

    ::

     # nnodes and nproc_per_node correspond to the ``torch.distributed.launch`` arguments. More
     # info about available arguments: https://pytorch.org/docs/stable/distributed.html#launch-utility
     trainer = torch_dist_role("trainer",container, entrypoint="trainer.py",.., nnodes=2, nproc_per_node=4)

    Args:
        name: Name of the role
        image: Image of the role
        entrypoint: Script or binary to launch
        resource: Resource specs that define the container properties. Predefined resources
            are supported as str arguments.
        args: Arguments to the script
        env: Env. variables to the worker
        num_replicas: Number of replicas
        max_retries: Number of retries
        retry_policy: ``torchx.specs.api.RetryPolicy``
        launch_kwargs: ``torch.distributed.launch`` arguments.

    Returns:
        Torchx role

    """
    dist_role_factory = load(
        "torchx.base",
        "dist_role",
        default=create_torch_dist_role,
    )

    resource = _resolve_resource(resource)

    return dist_role_factory(
        name,
        image,
        entrypoint,
        resource,
        base_image,
        args,
        env,
        num_replicas,
        max_retries,
        port_map or {},
        retry_policy,
        **launch_kwargs,
    )
