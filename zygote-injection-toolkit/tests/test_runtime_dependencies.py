import importlib
import unittest


class RuntimeDependencyTests(unittest.TestCase):
    def test_main_module_imports_without_stage2_dependencies(self) -> None:
        importlib.import_module("zygote_injection_toolkit.__main__")


if __name__ == "__main__":
    unittest.main()
