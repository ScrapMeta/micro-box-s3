"""Static integration checks, separate from host behavior and board acceptance."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ControlsIntegration(unittest.TestCase):
    def test_xiaozhi_uses_shared_single_touch_before_network(self):
        main=ROOT/'examples/xiaozhi/main'
        app=(main/'application.cc').read_text(encoding='utf-8')
        self.assertEqual(app.count('touch_button_ = std::make_unique<TouchButton>();'),1)
        self.assertLess(app.index('touch_button_ = std::make_unique<TouchButton>();'),app.index('board.StartNetwork();'))
        adapter=(main/'boards/common/touch_button.cc').read_text(encoding='utf-8')
        self.assertIn('micro_box_s3_inputs_create',adapter)
        self.assertIn('micro_box_s3_motor_create',adapter)
        self.assertNotIn('micro_box_s3_motor_pulse',adapter)
        self.assertIn('MICRO_BOX_S3_INPUT_TOUCH',adapter)
        self.assertNotRegex(adapter,r'TOUCH_PAD_NUM(?:12|13|14)\b')
        self.assertNotIn('touch_button_create(',adapter)
        cmake=(main/'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('micro_box_s3_controls',cmake)
    def test_only_one_touch_in_peripheral_example(self):
        s=(ROOT/'examples/peripherals/main/main.c').read_text(encoding='utf-8')
        self.assertNotRegex(s,r'TOUCH_PAD_NUM(?:12|13|14)\b')
        self.assertIn('micro_box_s3_inputs_create',s)
        self.assertIn('CONFIG_MICRO_BOX_S3_DEMO_BUTTONS',s)
        self.assertIn('CONFIG_MICRO_BOX_S3_DEMO_MOTOR',s)
        self.assertIn('CONFIG_MICRO_BOX_S3_DEMO_CONTROLS',s)
    def test_pin_header_matches_json(self):
        import json
        d=json.loads((ROOT/'board.json').read_text(encoding='utf-8'))
        h=(ROOT/'components/micro_box_s3/include/micro_box_s3_pins.h').read_text(encoding='utf-8')
        expected={'TOUCH_COUNT':1,'TOUCH_GPIO':11,'BUTTON_COUNT':2,'BUTTON_A_GPIO':12,'BUTTON_B_GPIO':13,'MOTOR_GPIO':14,'MOTOR_PWM_TIMER':1,'MOTOR_PWM_CHANNEL':1}
        for key,value in expected.items():self.assertRegex(h,r'#define\s+MICRO_BOX_S3_'+key+r'\s+'+str(value)+r'\b')
        self.assertEqual(d['touch_channels'],[11])
if __name__=='__main__':unittest.main()