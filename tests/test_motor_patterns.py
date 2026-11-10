import ctypes
from functools import lru_cache
from pathlib import Path
import tempfile
import unittest
from test_vb6824_parser import compile_library
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'examples/motor-patterns/main'
@lru_cache(maxsize=1)
def library():
    h=MAIN/'patterns.h'
    if not h.is_file():raise AssertionError('missing bounded pattern specification')
    base=ROOT/'.build/host';base.mkdir(parents=True,exist_ok=True)
    build=Path(tempfile.mkdtemp(prefix='motor_patterns_',dir=base))
    w=build/'wrapper.c';w.write_text('#include "'+h.as_posix()+'"\n#ifdef _WIN32\n#define API __declspec(dllexport)\n#else\n#define API\n#endif\nAPI int duration(unsigned i){return i<6?(int)patterns[i].duration_ms:-1;}\nAPI int duty(unsigned i){return i<6?(int)patterns[i].duty:-1;}\nAPI int take(unsigned*m,unsigned i){return pattern_take(m,i);}\n',encoding='utf-8')
    lib=compile_library(build,[w],'patterns')
    lib.take.argtypes=[ctypes.POINTER(ctypes.c_uint),ctypes.c_uint];lib.take.restype=ctypes.c_int
    return lib
class PatternTests(unittest.TestCase):
    def test_six_requested_cases(self):
        lib=library()
        self.assertEqual([(lib.duration(i),lib.duty(i)) for i in range(6)],[(100,100),(200,100),(400,100),(400,30),(400,60),(400,100)])
    def test_each_case_only_once_and_invalid_rejected(self):
        lib=library();m=ctypes.c_uint(0)
        for i in range(6):
            self.assertEqual(lib.take(ctypes.byref(m),i),1)
            self.assertEqual(lib.take(ctypes.byref(m),i),0)
        self.assertEqual(m.value,63)
        for i in [6,31,100,0xffffffff]:self.assertEqual(lib.take(ctypes.byref(m),i),0)
    def test_separate_stop_timer_and_no_auto_sequence_contract(self):
        p=MAIN/'main.c';self.assertTrue(p.is_file(),'missing motor pattern firmware')
        s=p.read_text(encoding='utf-8')
        for marker in ['LEDC_TIMER_1','LEDC_CHANNEL_1','esp_timer_start_once(stop_timer','MOTOR_OFF','REJECT','3000000','40000']:
            self.assertIn(marker,s)
        self.assertNotIn('touch_pad_',s)
        self.assertNotIn('esp_wifi',s)
        self.assertIn("command>='1' && command<='6'",s)
if __name__=='__main__':unittest.main()