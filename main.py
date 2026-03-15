import asyncio
import json
import os

from src.agent.agent import Agent
from src.models.project import Project
from src.plugins.plugin_collection.filesystem import set_allowed_directories, list_special_directories
from src.plugins.plugin_manager import register_plugin
from src.sensor.const import start_sensors
from src.sensor.feishu import start_lark_sensor

async def main():
    agent = Agent().load_checkpoint()
    start_lark_sensor(agent)
    await agent.sensor()

if __name__ == "__main__":
    a = Project(
        name="Project 1",
        prompt="测试所提供的工具能否正常使用",
        core="[2]openai:deepseek-chat",
        available_tools=["web"],
        available_workers=["[2]openai:deepseek-chat"]
    )
    for tool in ["database", "filesystem", "feishu", "manager", "schedule", "web"]:
        plugin = register_plugin(tool)
    with open(os.path.join(os.path.dirname(__file__), "data", "config", "file_config.json"), "r") as f:
        config = json.load(f)
        config = config["sandbox_dirs"]
    for test_dir in config:
        if not os.path.exists(test_dir):
            os.mkdir(test_dir)
    set_allowed_directories(config)
    print(list_special_directories())
    a.run_pipeline()
    start_sensors()
    asyncio.run(main())