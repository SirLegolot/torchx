#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import logging
import re
import sys
import threading
from queue import Queue
from typing import Optional
from urllib.parse import urlparse

from pyre_extensions import none_throws
from torchx import specs
from torchx.cli.cmd_base import SubCommand
from torchx.runner import Runner, get_runner
from torchx.specs.api import make_app_handle

logger: logging.Logger = logging.getLogger(__name__)

# only print colors if outputting directly to a terminal
if sys.stdout.isatty():
    GREEN = "\033[32m"
    ENDC = "\033[0m"
else:
    GREEN = ""
    ENDC = ""


def validate(job_identifier: str) -> None:
    if not re.match(r"^\w+://[^/.]*/[^/.]+/[^/.]+(/(\d+,?)+)?$", job_identifier):
        logger.error(
            f"{job_identifier} is not of the form SCHEDULER://[SESSION_NAME]/APP_ID/ROLE_NAME/[REPLICA_IDS,...]",
        )
        sys.exit(1)


def print_log_lines(
    runner: Runner,
    app_handle: str,
    role_name: str,
    replica_id: int,
    regex: str,
    should_tail: bool,
    exceptions: "Queue[Exception]",
) -> None:
    try:
        for line in runner.log_lines(
            app_handle, role_name, replica_id, regex, should_tail=should_tail
        ):
            print(f"{GREEN}{role_name}/{replica_id}{ENDC} {line}")
    except Exception as e:
        exceptions.put(e)
        raise


def get_logs(identifier: str, regex: Optional[str], should_tail: bool = False) -> None:
    validate(identifier)
    url = urlparse(identifier)
    scheduler_backend = url.scheme
    session_name = url.netloc or "default"

    # path is of the form ["", "app_id", "master", "0"]
    path = url.path.split("/")
    app_id = path[1]
    role_name = path[2]

    runner = get_runner(name=session_name)
    app_handle = make_app_handle(scheduler_backend, session_name, app_id)

    app = none_throws(runner.describe(app_handle))

    if len(path) == 4:
        replica_ids = [int(id) for id in path[3].split(",") if id]
    else:
        # print all replicas for the role
        num_replicas = find_role_replicas(app, role_name)

        if num_replicas is None:
            valid_ids = "\n".join(
                [
                    f"  {idx}: {scheduler_backend}://{app_id}/{role.name}"
                    for idx, role in enumerate(app.roles)
                ]
            )

            logger.error(
                f"No role [{role_name}] found for app: {app.name}."
                f" Did you mean one of the following:\n{valid_ids}",
            )
            sys.exit(1)

        replica_ids = list(range(0, num_replicas))

    threads = []
    exceptions = Queue()
    for replica_id in replica_ids:
        thread = threading.Thread(
            target=print_log_lines,
            args=(
                runner,
                app_handle,
                role_name,
                replica_id,
                regex,
                should_tail,
                exceptions,
            ),
        )
        thread.daemon = True
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    # Retrieve all exceptions, print all except one and raise the first recorded exception
    threads_exceptions = []
    while not exceptions.empty():
        threads_exceptions.append(exceptions.get())

    if len(threads_exceptions) > 0:
        for i in range(1, len(threads_exceptions)):
            logger.error(threads_exceptions[i])

        raise threads_exceptions[0]


def find_role_replicas(app: specs.AppDef, role_name: str) -> Optional[int]:
    for role in app.roles:
        if role_name == role.name:
            return role.num_replicas
    return None


class CmdLog(SubCommand):
    def add_arguments(self, subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--regex",
            type=str,
            help="regex filter",
        )

        subparser.add_argument(
            "-t",
            "--tail",
            action="store_true",
            help="Tail logs",
        )

        subparser.add_argument(
            "identifier",
            type=str,
            help="host identifier (scheduler_backend://[session_name]/app_id/role_name/replica_id)",
        )

    def run(self, args: argparse.Namespace) -> None:
        get_logs(args.identifier, args.regex, args.tail)
