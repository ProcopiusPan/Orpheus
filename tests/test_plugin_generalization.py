import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEXT_SURFACE = (
    ROOT / "README.md",
    ROOT / "docs/Fact维护说明.md",
    ROOT / "docs/安装便携包.md",
    ROOT / "docs/Zotero适配与使用.md",
    ROOT / "plugins/orpheus/references/facts.md",
    ROOT / "plugins/orpheus/references/obsidian.md",
    ROOT / "plugins/orpheus/references/workspace-notes.md",
    ROOT / "plugins/orpheus/references/paper-metadata-template.md",
    ROOT / "plugins/orpheus/references/agent-orchestration.md",
    ROOT / "plugins/orpheus/skills/research/SKILL.md",
)


def _surface_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in TEXT_SURFACE)


def test_user_facing_plugin_guidance_has_no_machine_or_development_specific_claims():
    text = _surface_text()
    forbidden = (
        r"GitHub\s*个人账号",
        r"GitHub\s*个人私有仓库",
        r"个人私有仓库计划",
        r"套餐",
        r"待落实",
        r"接口在实现时确定",
        r"尚未执行",
        r"最多同时运行两个",
        r"最多同时保留两个",
        r"已有两个研究",
        r"优先在 Zotero 主库",
        r"缺失文献再.*导入 Zotero",
        r"先计算\s+SHA(?:-256)?\s*并填写",
        r"要求非空\s*`?sha256`?",
        r"MISSING_PAPER_HASH",
    )
    for pattern in forbidden:
        assert not re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL), pattern


def test_concurrency_guidance_is_capacity_based():
    research = (ROOT / "plugins/orpheus/skills/research/SKILL.md").read_text(encoding="utf-8")
    orchestration = (ROOT / "plugins/orpheus/references/agent-orchestration.md").read_text(encoding="utf-8")
    for text in (research, orchestration):
        assert "宿主" in text and "并发" in text and "容量" in text
        assert "无限创建线程" in text
    assert "预留所需容量" in orchestration


def test_metadata_template_delegates_integrity_to_scripts():
    template = (ROOT / "plugins/orpheus/references/paper-metadata-template.md").read_text(encoding="utf-8")
    assert "由登记/同步脚本生成" in template
    assert "无需手工填写" in template
    assert "先计算" not in template
