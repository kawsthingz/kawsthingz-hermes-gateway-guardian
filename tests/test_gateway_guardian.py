import importlib.util
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "__init__.py"
spec = importlib.util.spec_from_file_location("gateway_guardian", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestClassify(unittest.TestCase):
    def test_ok(self):
        out = mod._classify(["gateway started", "poll ok", "delivery sent"])
        self.assertEqual(out["state"], "OK")

    def test_blocked_on_repeated_409(self):
        lines = [
            "terminated by other getUpdates request: 409 Conflict",
            "409 Conflict getUpdates",
            "409 polling conflict",
        ]
        out = mod._classify(lines)
        self.assertEqual(out["state"], "BLOCKED")

    def test_recover_never_executes(self):
        import tempfile

        old_home = mod._hermes_home
        with tempfile.TemporaryDirectory() as tmp:
            mod._hermes_home = lambda: Path(tmp)
            try:
                out = mod.gateway_guardian_recover({"action": "restart-gateway"})
                self.assertIn('"executes": false', out)
            finally:
                mod._hermes_home = old_home


if __name__ == "__main__":
    unittest.main()
