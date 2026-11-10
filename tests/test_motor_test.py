"""Host-C one-shot gate tests; source contracts are not hardware qualification."""
import ctypes
from functools import lru_cache
from pathlib import Path
import tempfile
import unittest
from test_vb6824_parser import compile_library
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'examples/motor-test/main'
@lru_cache(maxsize=1)
def load_gate():
    header=MAIN/'motor_gate.h'
    if not header.is_file():raise AssertionError('missing one-shot gate')
    base=ROOT/'.build/host';base.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='motor_gate_',dir=base))
    wrapper=tmp/'wrapper.c'
    wrapper.write_text('#include "'+header.as_posix()+'"\n#ifdef _WIN32\n#define API __declspec(dllexport)\n#else\n#define API\n#endif\nAPI int take(unsigned int*p){return motor_take(p);}\n',encoding='utf-8')
    lib=compile_library(tmp,[wrapper],'motor_gate')
    lib.take.argtypes=[ctypes.POINTER(ctypes.c_uint)];lib.take.restype=ctypes.c_int
    return lib
class MotorTests(unittest.TestCase):
    def test_exactly_one_pulse_per_boot(self):
        lib=load_gate();used=ctypes.c_uint(0)
        self.assertEqual(lib.take(ctypes.byref(used)),1)
        self.assertEqual(used.value,1)
        for _ in range(20):self.assertEqual(lib.take(ctypes.byref(used)),0)
    def test_preused_gate_rejects(self):
        lib=load_gate();used=ctypes.c_uint(1)
        self.assertEqual(lib.take(ctypes.byref(used)),0)
    def test_timer_and_command_safety_contract(self):
        p=MAIN/'main.c';self.assertTrue(p.is_file(),'missing bounded motor diagnostic')
        s=p.read_text(encoding='utf-8')
        self.assertIn('PULSE_US 200000',s)
        self.assertIn('esp_timer_start_once',s)
        self.assertIn("command=='V'",s)
        self.assertIn("command=='X'",s)
        self.assertIn('MOTOR_OFF',s)
        self.assertNotIn('touch_pad_',s)
        self.assertNotIn('esp_wifi',s)
        self.assertLess(s.index('esp_timer_start_once(stop_timer'),s.index('gpio_set_level(MOTOR_GPIO,1)'))
if __name__=='__main__':unittest.main()