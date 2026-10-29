import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('build_pengu_loader', ROOT / 'scripts' / 'build_pengu_loader.py')
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


class FindCppMsbuildTests(unittest.TestCase):
    def test_requires_the_cpp_toolset(self):
        # vswhere is asked for an install with the C++ toolset, so Build Tools without it are skipped
        with patch.object(build, '_run_vswhere', return_value=[]) as vswhere:
            self.assertIsNone(build._find_cpp_msbuild())
        self.assertIn('Microsoft.VisualStudio.Component.VC.Tools.x86.x64', vswhere.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
