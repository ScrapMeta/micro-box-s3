from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BuildContract(unittest.TestCase):
    def test_build_plan_is_isolated_and_never_flashes(self):
        path=ROOT/'tools/build.py'
        self.assertTrue(path.is_file(), 'missing portable build tool')
        spec=importlib.util.spec_from_file_location('micro_build',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        plans=[module.build_plan(name,ROOT,Path('/sdk/esp-idf'),'python',4) for name in module.TARGETS]
        expected={'display','audio','camera','touch','buttons','motor','controls','xiaozhi','controls-test','motor-test','motor-patterns'}
        self.assertEqual(set(module.TARGETS),expected)
        self.assertEqual(len({p['build_dir'] for p in plans}),len(expected))
        for target in ['controls-test','motor-test','motor-patterns']:
            p=module.build_plan(target,ROOT,Path('/sdk/esp-idf'),'python',4)
            self.assertEqual(Path(p['project_dir']).name,target)
            self.assertNotIn('CONFIG_MICRO_BOX_S3_DEMO_',p['overlay'])
        for target in ['touch','buttons','motor','controls']:
            p=module.build_plan(target,ROOT,Path('/sdk/esp-idf'),'python',4)
            self.assertIn('CONFIG_MICRO_BOX_S3_DEMO_'+target.upper()+'=y',p['overlay'])
        for p in plans:
            self.assertNotIn('flash',p['configure_command'])
            self.assertIn('-DIDF_TARGET=esp32s3',p['configure_command'])
            self.assertIn('--parallel',p['build_command'])
            self.assertTrue(p['build_dir'].startswith(str(ROOT/'.build')))
        audio=module.build_plan('audio',ROOT,Path('/sdk/esp-idf'),'python',4)
        self.assertIn('CONFIG_MICRO_BOX_S3_DEMO_AUDIO=y',audio['overlay'])
        self.assertIn('# CONFIG_MICRO_BOX_S3_DEMO_DISPLAY is not set',audio['overlay'])
        with self.assertRaises(ValueError):
            module.build_plan('unknown',ROOT,Path('/sdk/esp-idf'),'python',4)

    def test_build_plan_selects_working_size_optimization(self):
        spec=importlib.util.spec_from_file_location('micro_build_opt',ROOT/'tools/build.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for target in module.TARGETS:
            plan=module.build_plan(target,ROOT,Path('/sdk/esp-idf'),'python',4)
            self.assertIn('CONFIG_COMPILER_OPTIMIZATION_SIZE=y',plan['overlay'])

    def test_console_check_preserves_xiaozhi_secondary_usb(self):
        spec=importlib.util.spec_from_file_location('micro_build_console',ROOT/'tools/build.py')
        assert spec is not None and spec.loader is not None
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(hasattr(module,'console_configuration_valid'),
                        'console check must support existing xiaozhi secondary USB')
        primary={'ESP_CONSOLE_USB_SERIAL_JTAG':True}
        secondary={'ESP_CONSOLE_USB_SERIAL_JTAG':False,
                   'ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG':True}
        for target in module.TARGETS:
            self.assertTrue(module.console_configuration_valid(target,primary))
            self.assertFalse(module.console_configuration_valid(target,{}))
            self.assertEqual(module.console_configuration_valid(target,secondary),
                             target=='xiaozhi')

    def test_result_uses_actual_sdk_revision(self):
        spec=importlib.util.spec_from_file_location('micro_build_result',ROOT/'tools/build.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(hasattr(module,'build_result'),'missing SDK result formatter')
        value=module.build_result('display',{'version':'1.2','project_version':'1','git_revision':'v5.4.3'},[])
        self.assertEqual(value['sdk'],'ESP-IDF v5.4.3')
        self.assertFalse(value['flashed'])
        self.assertFalse(value['hardware_tested'])

if __name__=='__main__':
    unittest.main()
