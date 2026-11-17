"""定时事件的三类去向。"""

from src.timer.sinks.agent import agent_sink
from src.timer.sinks.graph import graph_sink
from src.timer.sinks.ui import ui_sink

__all__ = ["agent_sink", "graph_sink", "ui_sink"]
