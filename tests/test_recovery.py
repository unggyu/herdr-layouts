import unittest,sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'payload/mods/session-restore'))
import history,service
from options import build_argv
class RecoveryTests(unittest.TestCase):
 def test_yolo_defaults_and_options(self):
  r={'codex':'codex','session_id':'abc','options':['--full-auto','-s','read-only','--yolo','--sandbox=workspace-write','-a','never','-m','test','-p','work']}
  self.assertEqual(build_argv(r),['codex','--yolo','-m','test','-p','work','resume','abc'])
 def test_missing_options(self):
  self.assertEqual(build_argv({'codex':'codex','session_id':'abc'}),['codex','--yolo','resume','abc'])
 def test_prompt_guard(self):
  i={'state':'live','keep':True,'foreground':{'name':'powershell.exe'}}
  self.assertTrue(history.eligible(i,'PS C:\\work> '))
  self.assertFalse(history.eligible(i,'PS C:\\work> draft'))
  self.assertFalse(history.eligible({**i,'foreground':{'name':'wsl.exe'}},'PS C:\\work> '))
 def test_history_dedup_and_preservation(self):
  with tempfile.TemporaryDirectory() as d,patch.object(service,'DATA',Path(d)),patch.object(service,'read_state',return_value={'records':{}}):
   r={'session_id':'one','cwd':'/work'}
   history.save('t1','⠁ 제목',r);history.save('t1','⠂ 제목',r)
   self.assertEqual(len(history.entries()),1)
   history.save('t1','다음 제목');history.save('t1','다음 제목',{'session_id':'two'})
   self.assertEqual(len(history.entries()),2)
   self.assertEqual(history.entries()[-1]['record']['session_id'],'one')
 def test_cap_and_seed_no_resurrection(self):
  with tempfile.TemporaryDirectory() as d,patch.object(service,'DATA',Path(d)),patch.object(service,'read_state',return_value={'records':{'t1':{'title':'old','session_id':'a'}}}):
   history.seed()
   for n in range(105):history.save('t1',str(n))
   self.assertEqual(len(history.entries()),100)
   self.assertEqual(history.entries()[0]['title'],'104')
 def test_dispatch_never_types_into_program(self):
  with patch.object(history,'lookup',return_value=('t1',{'session_id':'abc'})),patch.object(service,'hc',side_effect=[json.dumps({'state':'live','keep':True,'foreground':{'name':'wsl.exe'}}),'PS C:\\work>']),patch.object(service,'send_restore') as send:
   with self.assertRaises(ValueError):history.dispatch('entry')
   send.assert_not_called()
 def test_launch_subprocess_uses_selected_entry(self):
  import subprocess,os
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);fake=root/'fake-codex'
   fake.write_text('#!/usr/bin/python3\nimport sys,json,os\nprint(json.dumps({"args":sys.argv[1:],"cwd":os.getcwd()}))\n');fake.chmod(0o700)
   record={'codex':str(fake),'session_id':'test-recovery-id','cwd':d,'codex_home':d,'options':['-m','test']}
   (root/'sessions.json').write_text(json.dumps({'records':{'t1':record}}))
   with patch.object(service,'DATA',root):history.save('t1','test',record);entry=history.entries()[0]['id']
   launch=Path(history.__file__).with_name('launch.py')
   result=subprocess.run([sys.executable,str(launch),str(root/'sessions.json'),'t1',entry],capture_output=True,text=True,env={**os.environ,'HOME':d})
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(json.loads(result.stdout),{'args':['--yolo','-m','test','resume','test-recovery-id'],'cwd':d})
if __name__=='__main__':unittest.main()
