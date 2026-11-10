"""流式响应的纯拼装逻辑（SPEC-006）。"""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.streaming import StreamAssembler
from tests.support.fakes import chunk, delta, tool_delta


def test_assembler_merges_content_reasoning_and_split_tool_calls():
    assembler = StreamAssembler()
    assembler.add(
        chunk(
            delta=delta(
                reasoning="先",
                tool_calls=[
                    tool_delta(
                        0,
                        call_id="c1",
                        type="function",
                        name="read_",
                        arguments='{"p":',
                    )
                ],
            )
        )
    )
    assembler.add(
        chunk(
            delta=delta(
                content="你",
                reasoning="想",
                tool_calls=[tool_delta(0, name="file", arguments=' "a"}')],
            )
        )
    )
    assembler.add(chunk(delta=delta(content="好")))
    assembler.add(chunk(usage=SimpleNamespace(total_tokens=7)))

    message = assembler.build()

    assert message.content == "你好"
    assert message.reasoning_content == "先想"
    assert message.tool_calls[0].id == "c1"
    assert message.tool_calls[0].function.name == "read_file"
    assert message.tool_calls[0].function.arguments == '{"p": "a"}'
    assert assembler.usage.total_tokens == 7


def test_assembler_sorts_tool_calls_by_stream_index():
    assembler = StreamAssembler()
    assembler.add(chunk(delta=delta(tool_calls=[tool_delta(2, call_id="c", name="c")])))
    assembler.add(chunk(delta=delta(tool_calls=[tool_delta(0, call_id="a", name="a")])))
    assembler.add(chunk(delta=delta(tool_calls=[tool_delta(1, call_id="b", name="b")])))

    message = assembler.build()

    assert [call.id for call in message.tool_calls] == ["a", "b", "c"]


def test_assembler_reads_reasoning_from_model_dump_and_skips_empty_frames():
    class DumpDelta:
        content = None
        tool_calls = None

        def model_dump(self):
            return {"reasoning_content": "兜底"}

    assembler = StreamAssembler()
    assembler.add(
        SimpleNamespace(choices=[SimpleNamespace(delta=DumpDelta())], usage=None)
    )
    assembler.add(SimpleNamespace(choices=[], usage=None))

    assert assembler.build().reasoning_content == "兜底"


def test_assembler_without_reasoning_omits_attribute():
    assembler = StreamAssembler()
    assembler.add(chunk(delta=delta(content="ok")))

    message = assembler.build()

    assert message.tool_calls is None
    assert not hasattr(message, "reasoning_content")
