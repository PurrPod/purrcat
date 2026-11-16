"""AgentLoop 节点工作空间隔离：同名任务不得共用 taskspace。"""

from __future__ import annotations

import os

from src.harness.node.extensions.agent_loop.node import (
    SANDBOX_TASKSPACE_ROOT,
    taskspace_paths,
)


def test_same_name_different_tasks_get_isolated_dirs():
    host_a, sandbox_a = taskspace_paths("报告", "task_a", "nd_agent")
    host_b, sandbox_b = taskspace_paths("报告", "task_b", "nd_agent")

    assert host_a != host_b
    assert sandbox_a != sandbox_b


def test_same_task_reuses_the_same_dir_across_resume():
    assert taskspace_paths("报告", "task_a", "nd_agent") == taskspace_paths(
        "报告", "task_a", "nd_agent"
    )


def test_taskspace_paths_are_name_readable_and_sandbox_mapped():
    host, sandbox = taskspace_paths("报告", "task_a", "nd_agent")

    assert os.path.basename(os.path.dirname(host)) == "报告_task_a"
    assert os.path.basename(host) == "nd_agent"
    assert sandbox == f"{SANDBOX_TASKSPACE_ROOT}/报告_task_a/nd_agent"


def test_nodes_of_the_same_task_get_separate_dirs():
    host_a, _ = taskspace_paths("报告", "task_a", "nd_agent")
    host_b, _ = taskspace_paths("报告", "task_a", "nd_other")

    assert host_a != host_b
