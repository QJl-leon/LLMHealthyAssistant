"""One low quality image, sequential requests, no external model call."""
import base64
import io
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from dotenv import dotenv_values
from PIL import Image

OUT=Path('/home/ubuntu/RAG-job/线上测试部署')
RUN='server-check-20261017'
RESULT=OUT/'results'/RUN
c=dotenv_values(OUT/'测试账号.env')
base=c['RAG_BASE_URL']
headers={'X-Run-Id':RUN,'X-Trace-Id':RUN+'-probe'}

def request(path,data=None,token='',content_type='application/json'):
 h={**headers}
 if token:h['Authorization']='Bearer '+token
 if data is not None:h['Content-Type']=content_type
 req=Request(base+path,data=data,headers=h)
 with urlopen(req,timeout=30) as resp:return json.load(resp)

login=request('/api/v1/auth/login',json.dumps({'email':c['RAG_TEST_EMAIL'],'password':c['RAG_TEST_PASSWORD'],'tenant_id':c['RAG_TEST_TENANT_ID']}).encode())
token=login['data']['access_token']
# A deterministic, synthetic 1x1 PNG. Pillow only encodes the fixture; no patient data.
buf=io.BytesIO();Image.new('RGB',(1,1),(128,128,128)).save(buf,format='PNG');image=buf.getvalue()
boundary='lha-observation-fixture'
body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="server-probe.png"\r\nContent-Type: image/png\r\n\r\n').encode()+image+f'\r\n--{boundary}--\r\n'.encode()
start=time.monotonic()
upload=request('/api/v1/uploads',body,token,'multipart/form-data; boundary='+boundary)
assert upload['code']==0,upload
key=upload['data']['image_key']
payload=json.dumps({'client_task_id':RUN+'-quality-probe','images':[{'key':key,'position':'lab_sheet'}],'institution':'SYNTHETIC_DEPLOYMENT_PROBE'}).encode()
created=request('/api/v1/tasks',payload,token)
assert created['code']==0,created
first=created['data'];task=first['task_id']
repeated=request('/api/v1/tasks',payload,token)
assert repeated['data']['task_id']==task and repeated['data']['is_new'] is False
req=Request(base+'/api/v1/tasks/'+task+'/events',headers={**headers,'Authorization':'Bearer '+token})
events=[];first_event=None
with urlopen(req,timeout=30) as stream:
 assert 'text/event-stream' in stream.headers.get('Content-Type','')
 for raw in stream:
  line=raw.decode().strip()
  if line.startswith('data:'):
   event=json.loads(line[5:].strip())
   if first_event is None:first_event=time.monotonic()-start
   events.append({'at_seconds':time.monotonic()-start,'event':event})
   if 'result' in event:break
assert any(e['event'].get('result',{}).get('status')=='awaiting_images' for e in events),events
cost=request('/api/v1/tasks/'+task+'/cost',token=token)
# No OCR/VLM/LLM/retrieval invocation is expected for this deliberately invalid sample.
summary={'run_id':RUN,'kind':'deployment_quality_gate_probe_not_load_test','task_id':task,'trace_id':first.get('trace_id'),
         'upload_ok':True,'duplicate_submission_reused_task':True,'sse_received':True,'terminal_status':'awaiting_images',
         'first_business_event_seconds':first_event,'elapsed_seconds':time.monotonic()-start,'cost_response':cost,
         'report_generated':False,'fixture':'synthetic 1x1 PNG; intentionally fails local quality gate'}
(RESULT/'deployment-probe.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
(RESULT/'sse-events.json').write_text(json.dumps(events,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in summary.items() if k!='cost_response'},ensure_ascii=False,indent=2))
