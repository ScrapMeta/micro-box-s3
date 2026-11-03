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
        self.assertEqual(len({p['build_dir'] for p in plans}),5)
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
