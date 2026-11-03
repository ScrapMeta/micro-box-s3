"""Build examples in an exported ESP-IDF shell; never opens a serial port."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

TARGETS=('display','audio','camera','touch','xiaozhi')

def build_plan(target, root, idf, python, jobs):
    if target not in TARGETS:
        raise ValueError('unknown build target')
    root=Path(root).resolve();idf=Path(idf)
    project=root/'examples'/('xiaozhi' if target=='xiaozhi' else 'peripherals')
    build=root/'.build'/target
    overlay='CONFIG_COMPILER_OPTIMIZATION_SIZE=y\n'
    if target!='xiaozhi':
        for mode in TARGETS[:-1]:
            key='CONFIG_MICRO_BOX_S3_DEMO_'+mode.upper()
            overlay+=(key+'=y\n') if mode==target else ('# '+key+' is not set\n')
    defaults=(project/'sdkconfig.defaults').as_posix()+';'+(build/'defaults.generated').as_posix()
    configure=[str(python),str(idf/'tools/idf.py'),'-C',str(project),'-B',str(build),
        '-DIDF_TARGET=esp32s3','-DSDKCONFIG='+(build/'sdkconfig').as_posix(),
        '-DSDKCONFIG_DEFAULTS='+defaults,'reconfigure']
    return {'target':target,'project_dir':str(project),'build_dir':str(build),'overlay':overlay,
        'configure_command':configure,'build_command':['cmake','--build',str(build),'--parallel',str(jobs)]}

def build_result(target, description, images):
    return {'target':target,'board':'micro-box-s3','sdk':'ESP-IDF '+description['git_revision'],
        'built_at':datetime.now(timezone.utc).isoformat(),'compile_passed':True,
        'configuration_verified':True,'flashed':False,'hardware_tested':False,'images':images}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',choices=TARGETS+('all',))
    parser.add_argument('--jobs',type=int,default=4)
    args=parser.parse_args()
    if args.jobs<1:
        parser.error('--jobs must be positive')
    idf=os.environ.get('IDF_PATH')
    if not idf or not (Path(idf)/'tools/idf.py').is_file():
        parser.error('Export the ESP-IDF environment first (IDF_PATH and its Python environment).')
    root=Path(__file__).resolve().parents[1]
    selected=TARGETS if args.target=='all' else (args.target,)
    for target in selected:
        plan=build_plan(target,root,Path(idf),sys.executable,args.jobs)
        output=Path(plan['build_dir']);output.mkdir(parents=True,exist_ok=True)
        (output/'defaults.generated').write_text(plan['overlay'],encoding='utf-8')
        (output/'commands.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
        for stage in ('configure','build'):
            command=plan[stage+'_command']
            print(target,stage,flush=True)
            with (output/(stage+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                print((output/(stage+'.log')).read_text(encoding='utf-8',errors='replace')[-10000:])
                return result.returncode
        cfg=json.loads((output/'config/sdkconfig.json').read_text(encoding='utf-8'))
        assert cfg['IDF_TARGET']=='esp32s3'
        assert cfg.get('LCD_GC9A01_160X160')
        assert not cfg.get('VB6824_OTA_SUPPORT')
        assert cfg.get('ESPTOOLPY_FLASHSIZE')=='16MB'
        if target=='xiaozhi':
            assert cfg.get('BOARD_TYPE_MICRO_BOX_S3')
            assert cfg.get('USE_EYE_STYLE_VB6824')
        else:
            assert cfg.get('MICRO_BOX_S3_DEMO_'+target.upper())
            assert sum(bool(cfg.get('MICRO_BOX_S3_DEMO_'+x.upper())) for x in TARGETS[:-1])==1
        manifest=json.loads((output/'flasher_args.json').read_text(encoding='utf-8'))
        images=[]
        for address,name in manifest['flash_files'].items():
            data=(output/name).read_bytes()
            assert int(address,0)+len(data)<=16*1024*1024
            images.append({'offset':address,'file':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        description=json.loads((output/'project_description.json').read_text(encoding='utf-8'))
        report=build_result(target,description,images)
        (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PASS',target,flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
