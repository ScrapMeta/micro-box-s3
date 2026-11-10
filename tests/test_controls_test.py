"""Real host C debounce behavior plus separately labelled firmware safety contracts."""
import ctypes
from functools import lru_cache
from pathlib import Path
import tempfile
import unittest
from test_vb6824_parser import compile_library
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'examples/controls-test'
class State(ctypes.Structure):
    _fields_=[('stable',ctypes.c_uint32),('candidate',ctypes.c_uint32),('changed_at',ctypes.c_uint32)]
@lru_cache(maxsize=1)
def library():
    header=PROJECT/'main/input_logic.h'
    if not header.is_file():raise AssertionError('missing actual C input logic')
    build=ROOT/'.build/host';build.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='controls_',dir=build))
    source=tmp/'wrapper.c'
    source.write_text('#include "'+header.as_posix()+'"\n'
        '#ifdef _WIN32\n#define API __declspec(dllexport)\n#else\n#define API\n#endif\n'
        'API void init(input_state_t*s,uint32_t v,uint32_t t){input_init(s,v,t);}\n'
        'API int step(input_state_t*s,uint32_t v,uint32_t t){return input_step(s,v,t,25);}\n'
        'API unsigned int touch(unsigned int b,unsigned int r,unsigned int p){return touch_candidate(b,r,p);}\n',encoding='utf-8')
    lib=compile_library(tmp,[source],'controls_logic')
    lib.init.argtypes=[ctypes.POINTER(State),ctypes.c_uint32,ctypes.c_uint32]
    lib.step.argtypes=[ctypes.POINTER(State),ctypes.c_uint32,ctypes.c_uint32]
    lib.step.restype=ctypes.c_int
    return lib
class DebounceBehavior(unittest.TestCase):
    def test_press_requires_25ms_stability(self):
        lib=library();s=State();lib.init(ctypes.byref(s),1,0)
        self.assertEqual(lib.step(ctypes.byref(s),0,10),0)
        self.assertEqual(lib.step(ctypes.byref(s),0,34),0)
        self.assertEqual(lib.step(ctypes.byref(s),0,35),1)
        self.assertEqual(s.stable,0)
    def test_bounce_does_not_emit(self):
        lib=library();s=State();lib.init(ctypes.byref(s),1,0)
        for value,now in [(0,5),(1,10),(0,15),(1,20)]:
            self.assertEqual(lib.step(ctypes.byref(s),value,now),0)
        self.assertEqual(s.stable,1)
    def test_release_and_held_have_no_repeats(self):
        lib=library();s=State();lib.init(ctypes.byref(s),0,0)
        self.assertEqual(lib.step(ctypes.byref(s),0,5000),0)
        self.assertEqual(lib.step(ctypes.byref(s),1,5010),0)
        self.assertEqual(lib.step(ctypes.byref(s),1,5035),1)
        self.assertEqual(lib.step(ctypes.byref(s),1,9000),0)
    def test_timestamp_wrap(self):
        lib=library();s=State();lib.init(ctypes.byref(s),1,0xffffffe0)
        self.assertEqual(lib.step(ctypes.byref(s),0,0xfffffff0),0)
        self.assertEqual(lib.step(ctypes.byref(s),0,9),1)
class TouchBehavior(unittest.TestCase):
    def test_positive_delta_hysteresis(self):
        header=(PROJECT/'main/input_logic.h').read_text(encoding='utf-8')
        self.assertIn('touch_candidate(',header,'missing S3 touch hysteresis implementation')
        lib=library();lib.touch.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.c_uint32];lib.touch.restype=ctypes.c_uint32
        self.assertEqual(lib.touch(1000,1099,0),0)
        self.assertEqual(lib.touch(1000,1100,0),1)
        self.assertEqual(lib.touch(1000,1070,1),1)
        self.assertEqual(lib.touch(1000,1049,1),0)
        self.assertEqual(lib.touch(0,1000,0),0)
class FirmwareSafetyContract(unittest.TestCase):
    def test_no_motor_activation_and_one_touch_channel(self):
        p=PROJECT/'main/main.c'
        self.assertTrue(p.is_file(),'missing motor-locked offline diagnostic')
        source=p.read_text(encoding='utf-8')
        self.assertIn('TOUCH_PAD_NUM11',source)
        self.assertNotIn('TOUCH_PAD_NUM12',source)
        self.assertNotIn('TOUCH_PAD_NUM13',source)
        self.assertNotIn('TOUCH_PAD_NUM14',source)
        self.assertIn('MOTOR_LOCKED',source)
        self.assertNotRegex(source,r'gpio_set_level\(MOTOR_GPIO,\s*1\)')
        self.assertNotIn('ledc_set_duty',source)
        self.assertNotIn('esp_wifi',source)
if __name__=='__main__':unittest.main()