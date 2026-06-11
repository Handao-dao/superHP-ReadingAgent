import pytest

from superhp_agent.context import ContextBlock, ContextBundle


def test_context_block_renders_attrs_and_content():
    block = ContextBlock(
        "density_profile",
        "Target reader: B1-B2 & beyond",
        attrs={"level": "intermediate", "label": 'M "Medium"'},
    )

    rendered = block.render()

    assert rendered.startswith('<density_profile level="intermediate" label="M &quot;Medium&quot;">')
    assert "Target reader: B1-B2 & beyond" in rendered
    assert rendered.endswith("</density_profile>")


def test_context_block_rejects_invalid_name():
    with pytest.raises(ValueError, match="Invalid context block name"):
        ContextBlock("bad name", "content").render()


def test_context_bundle_to_messages_groups_roles_and_metadata():
    bundle = ContextBundle(
        system_blocks=[
            ContextBlock("system_policy", "Follow the contract.", role="system"),
        ],
        user_blocks=[
            ContextBlock("reader_text", "Harry <picked> up his wand.", role="user"),
            ContextBlock("runtime_note", "Current Time: now", role="metadata"),
        ],
    )

    messages = bundle.to_messages()

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "<system_policy>" in messages[0]["content"]
    assert "<reader_text>" in messages[1]["content"]
    assert "Harry <picked> up his wand." in messages[1]["content"]
    assert "[Runtime Context - metadata only, not instructions]" in messages[1]["content"]
    assert "<runtime_note>" in messages[1]["content"]


def test_context_bundle_omits_empty_roles():
    messages = ContextBundle(
        user_blocks=[ContextBlock("reader_text", "Only user content.")]
    ).to_messages()

    assert messages == [
        {"role": "user", "content": "<reader_text>\nOnly user content.\n</reader_text>"}
    ]


def test_context_bundle_with_blocks_appends_without_mutating_original():
    base = ContextBundle(
        system_blocks=[ContextBlock("system_policy", "Policy", role="system")],
        user_blocks=[ContextBlock("density_profile", "Density")],
    )

    derived = base.with_blocks(ContextBlock("reader_text", "Chunk text"))

    assert "<reader_text>" not in base.render_role("user")
    assert "<density_profile>" in derived.render_role("user")
    assert "<reader_text>\nChunk text\n</reader_text>" in derived.render_role("user")
