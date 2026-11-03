from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CmakeEarlyExpansion(unittest.TestCase):
    def test_requirements_scan_does_not_require_kconfig_values(self):
        cmake=shutil.which('cmake')
        if not cmake:
            candidates=sorted((Path.home()/'.espressif/tools/cmake').glob('*/bin/cmake.exe'))
            cmake=str(candidates[-1]) if candidates else None
        if not cmake:
            self.skipTest('CMake is not installed')
        work=ROOT/'.build/cmake-contract';work.mkdir(parents=True,exist_ok=True)
        script=work/'early.cmake'
        # ESP-IDF early expansion's registration macro returns from the include.
        script.write_text('cmake_minimum_required(VERSION 3.16)\n'
            'macro(idf_component_register)\n message(STATUS \"REACHED_REGISTRATION\")\n return()\nendmacro()\n'
            'include(\"'+(ROOT/'examples/xiaozhi/main/CMakeLists.txt').as_posix()+'\")\n',encoding='utf-8')
        result=subprocess.run([cmake,'-P',str(script)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertIn('REACHED_REGISTRATION',result.stdout)

if __name__=='__main__':
    unittest.main()
