import json,pathlib,subprocess,sys,tempfile,unittest
root=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));import checkpoint
class CliTest(unittest.TestCase):
 def test_save_verify_and_stale_refusal(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=pathlib.Path(tmp);repo=base/'repo';repo.mkdir()
   def git(*a):subprocess.run(['git','-C',str(repo),*a],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   git('init');git('config','user.email','synthetic@example.invalid');git('config','user.name','synthetic');(repo/'state').write_text('first');git('add','state');git('commit','-m','fixture')
   d={x:[{'text':'UNKNOWN','source':'synthetic','status':'unknown'}] for x in checkpoint.FIELDS};d['processes']={'inventory':'UNKNOWN','inventory_source':'not verified','observed_at':'UNKNOWN','items':[]};d['objective']=[{'text':'preserve blue','source':'user instruction','status':'fact'}];d['restrictions']=[{'text':'no trading','source':'user instruction','status':'fact'}];d['next_action']=[{'text':'verify','source':'test','status':'fact'}]
   src=base/'input.json';cp=base/'handoff.json';src.write_text(json.dumps(d));cmd=[sys.executable,str(root/'checkpoint.py')]
   subprocess.run(cmd+['write','--input',str(src),'--output',str(cp),'--repo',str(repo),'--expected','ABSENT'],check=True,capture_output=True)
   v=subprocess.run(cmd+['verify','--file',str(cp),'--repo',str(repo)],check=True,capture_output=True,text=True);result=json.loads(v.stdout);self.assertEqual(result['data']['restrictions'][0]['text'],'no trading');self.assertFalse(result['automatic_acceptance'])
   (repo/'state').write_text('second');v=subprocess.run(cmd+['verify','--file',str(cp),'--repo',str(repo)],capture_output=True,text=True);self.assertEqual(v.returncode,2);self.assertIn('changed_files',json.loads(v.stdout)['source_differences'])
if __name__=='__main__':unittest.main()
