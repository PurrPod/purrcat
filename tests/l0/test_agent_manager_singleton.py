"""Agent 门面与 manager 模块必须共享同一个 AgentManager 单例。"""

from __future__ import annotations

import src.agent as facade
from src.agent import manager as manager_module


def test_manager_is_a_singleton():
    assert manager_module.AgentManager() is manager_module.manager


def test_facade_reuses_the_same_manager_instance():
    assert facade._manager_instance is manager_module.manager


def test_facade_functions_are_bound_to_the_shared_instance():
    assert facade.init_agent.__self__ is manager_module.manager
    assert facade.get_active_session_id.__self__ is manager_module.manager
