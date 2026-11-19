"""打包与入口的静态校验（不联网、不真的 pip install）。

pip 安装需要拉 setuptools，离线机器上装不了；所以这里校验"元数据正确"，
真正的安装留给有网的机器。
"""

from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestPackaging(unittest.TestCase):
    def setUp(self) -> None:
        self.data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_project_metadata(self) -> None:
        project = self.data["project"]
        self.assertEqual(project["name"], "boss-screening")
        self.assertTrue(project["version"])
        self.assertIn("MIT", str(project["license"]))

    def test_console_script_points_at_main(self) -> None:
        self.assertEqual(self.data["project"]["scripts"]["bosscreen"], "bosscreen.cli:main")

    def test_src_layout(self) -> None:
        self.assertEqual(self.data["tool"]["setuptools"]["packages"]["find"]["where"], ["src"])

    def test_python_floor(self) -> None:
        self.assertIn(">=3.11", self.data["project"]["requires-python"])

    def test_no_runtime_dependencies(self) -> None:
        self.assertEqual(self.data["project"]["dependencies"], [], "核心链路应该零依赖")

    def test_entrypoint_is_importable(self) -> None:
        from bosscreen.cli import main

        self.assertTrue(callable(main))

    def test_version_matches(self) -> None:
        import bosscreen

        self.assertEqual(bosscreen.__version__, self.data["project"]["version"])


if __name__ == "__main__":
    unittest.main()
