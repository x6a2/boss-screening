"""需求方案：多份并存、切换、以及"改名就是另存为新方案"。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.models import Candidate  # noqa: E402
from bosscreen.requirement import requirement_from_dict, requirement_to_dict  # noqa: E402
from bosscreen.scoring import rank  # noqa: E402
from bosscreen.store import Store  # noqa: E402
from bosscreen.web import Board  # noqa: E402

CANDS = [
    Candidate(uid="a", name="甲", degree="硕士", work_years=6.0, expect_city=["深圳"], skills=["Python"]),
    Candidate(uid="b", name="乙", degree="本科", work_years=3.0, expect_city=["广州"], skills=["Go"]),
]

STRICT = {"name": "严格版", "threshold": 70,
          "must": [{"field": "degree", "op": "gte", "value": "硕士"}],
          "nice": [{"field": "skills", "op": "contains_any", "value": ["Python"], "weight": 3}]}
LOOSE = {"name": "放宽版", "threshold": 40,
         "must": [{"field": "work_years", "op": "gte", "value": "3"}],
         "nice": [{"field": "skills", "op": "contains_any", "value": ["Go"], "weight": 2}]}


class TestStoreSchemes(unittest.TestCase):
    def test_roundtrip_two_schemes(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.db")
            store.save_requirement("严格版", "严格版", STRICT)
            store.save_requirement("放宽版", "放宽版", LOOSE)
            names = [s["name"] for s in store.list_requirements()]
            self.assertEqual(set(names), {"严格版", "放宽版"})
            self.assertEqual(store.load_requirement("放宽版")["threshold"], 40)
            self.assertIsNone(store.load_requirement("不存在"))
            store.close()

    def test_saving_same_id_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.db")
            store.save_requirement("x", "旧名", STRICT)
            store.save_requirement("x", "新名", LOOSE)
            rows = store.list_requirements()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "新名")
            store.close()


class TestBoardSchemes(unittest.TestCase):
    def _board(self):
        schemes: dict[str, dict] = {}
        saved: list[dict] = []

        def on_save(req, spec):
            schemes[req.name] = spec
            saved.append(spec)

        def list_schemes():
            return [{"id": k, "name": k} for k in schemes]

        def load_scheme(sid):
            spec = schemes.get(sid)
            return (requirement_from_dict(spec), spec) if spec else None

        board = Board(rank(CANDS, requirement_from_dict(LOOSE)), requirement_from_dict(LOOSE),
                      CANDS, on_save=on_save, list_schemes=list_schemes, load_scheme=load_scheme)
        return board, schemes, saved

    def test_saving_under_new_name_adds_a_scheme(self):
        board, schemes, saved = self._board()
        board.apply(STRICT)
        board.apply(dict(LOOSE, name="第三版"))
        self.assertEqual(set(schemes), {"严格版", "第三版"})
        self.assertEqual(len(saved), 2)
        self.assertEqual(len(board.payload()["schemes"]), 2)

    def test_switch_changes_ranking_without_saving(self):
        board, schemes, saved = self._board()
        board.apply(STRICT)          # 严格版：只有硕士过
        strict_top = board.payload()["rows"][0]["name"]
        payload = board.switch_scheme("严格版")
        self.assertEqual(payload["req"]["name"], "严格版")
        self.assertEqual(payload["rows"][0]["name"], strict_top)
        self.assertEqual(len(saved), 1, "切方案不是改方案，不该再写一次库")
        self.assertEqual(len(payload["schemes"]), 1)

    def test_switch_to_missing_scheme_raises(self):
        board, _schemes, _saved = self._board()
        with self.assertRaises(KeyError):
            board.switch_scheme("没有这个")

    def test_no_load_callback_raises_keyerror(self):
        board = Board(rank(CANDS, requirement_from_dict(LOOSE)), requirement_from_dict(LOOSE), CANDS)
        with self.assertRaises(KeyError):
            board.switch_scheme("x")

    def test_payload_has_empty_schemes_when_mock(self):
        board = Board(rank(CANDS, requirement_from_dict(LOOSE)), requirement_from_dict(LOOSE), CANDS)
        self.assertEqual(board.payload()["schemes"], [])


if __name__ == "__main__":
    unittest.main()
