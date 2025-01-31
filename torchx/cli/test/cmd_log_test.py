#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import io
import unittest
from typing import Iterator, Optional
from unittest.mock import MagicMock, patch

from torchx.cli.cmd_log import ENDC, GREEN, get_logs
from torchx.specs import AppDef, Role, parse_app_handle


class SentinelError(Exception):
    """
    Used to mock sys.exit
    """

    pass


RUNNER = "torchx.cli.cmd_log.get_runner"


class MockRunner:
    def __call__(self, name: Optional[str] = None) -> "MockRunner":
        return self

    def describe(self, app_handle: str) -> AppDef:
        scheduler_backend, session_name, app_id = parse_app_handle(app_handle)
        return AppDef(
            name=app_id,
            roles=[
                Role(name="master", image="test_image", num_replicas=1),
                Role(name="trainer", image="test_image", num_replicas=3),
            ],
        )

    def log_lines(
        self,
        app_id: str,
        role_name: str,
        k: str,
        regex: str,
        since: Optional[int] = None,
        until: Optional[int] = None,
        should_tail: bool = False,
    ) -> Iterator[str]:
        import re

        if regex is None:
            regex = ".*"

        log_lines = ["INFO foo", "ERROR bar", "WARN baz"]
        return iter([line for line in log_lines if re.match(regex, line)])


class CmdLogTest(unittest.TestCase):
    @patch("sys.exit", side_effect=SentinelError)
    def test_cmd_log_bad_job_identifier(self, exit_mock: MagicMock) -> None:
        with self.assertRaises(SentinelError):
            get_logs("local:///SparseNNAppDef/", "QPS.*")
        exit_mock.assert_called_once_with(1)

    @patch(RUNNER, new_callable=MockRunner)
    @patch("sys.exit", side_effect=SentinelError)
    def test_cmd_log_unknown_role(
        self, exit_mock: MagicMock, mock_runner: MagicMock
    ) -> None:
        with self.assertRaises(SentinelError):
            get_logs(
                "local://default/SparseNNAppDef/unknown_role",
                regex=None,
            )

        exit_mock.assert_called_once_with(1)

    @patch(RUNNER, new_callable=MockRunner)
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_log_all_replicas(
        self, stdout_mock: MagicMock, mock_runner: MagicMock
    ) -> None:
        get_logs("local://test-session/SparseNNAppDef/trainer", regex="INFO")
        self.assertSetEqual(
            {
                f"{GREEN}trainer/0{ENDC} INFO foo",
                f"{GREEN}trainer/1{ENDC} INFO foo",
                f"{GREEN}trainer/2{ENDC} INFO foo",
                # print writes the final newline so we
                # end up with an empty string when we split by \n
                "",
            },
            set(stdout_mock.getvalue().split("\n")),
        )

    @patch(RUNNER, new_callable=MockRunner)
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_log_one_replica(
        self, stdout_mock: MagicMock, mock_runner: MagicMock
    ) -> None:
        get_logs("local://test-session/SparseNNAppDef/trainer/0", regex=None)
        self.assertSetEqual(
            {
                f"{GREEN}trainer/0{ENDC} INFO foo",
                f"{GREEN}trainer/0{ENDC} ERROR bar",
                f"{GREEN}trainer/0{ENDC} WARN baz",
                # print writes the final newline so we
                # end up with an empty string when we split by \n
                "",
            },
            set(stdout_mock.getvalue().split("\n")),
        )

    @patch(RUNNER, new_callable=MockRunner)
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_log_some_replicas(
        self, stdout_mock: MagicMock, mock_runner: MagicMock
    ) -> None:
        get_logs("local://test-session/SparseNNAppDef/trainer/0,2", regex="WARN")
        self.assertSetEqual(
            {
                f"{GREEN}trainer/0{ENDC} WARN baz",
                f"{GREEN}trainer/2{ENDC} WARN baz",
                # print writes the final newline so we
                # end up with an empty string when we split by \n
                "",
            },
            set(stdout_mock.getvalue().split("\n")),
        )

    @patch(RUNNER, new_callable=MockRunner)
    def test_print_log_lines_throws(self, mock_runner: MagicMock) -> None:
        # makes sure that when the function executed in the threadpool
        # errors out; we raise the exception all the way through
        with patch.object(mock_runner, "log_lines") as log_lines_mock:
            log_lines_mock.side_effect = RuntimeError
            with self.assertRaises(RuntimeError):
                get_logs("local://test-session/SparseNNAppDef/trainer/0,1", regex=None)
