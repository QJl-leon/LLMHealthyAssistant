"""Create one normal user in a dedicated tenant; keep password out of reports."""
import json
import os
from pathlib import Path
import secrets
import uuid
from urllib.request import Request, urlopen
from dotenv import dotenv_values
OUT=Path('/home/ubuntu/RAG-job/线上测试部署')
secret=OUT/'测试账号.env'
if secret.exists():
 data=dotenv_values(secret)
else:
 data={'RAG_BASE_URL':'https://www.smproject.site','RAG_TEST_EMAIL':'rag-perf-'+secrets.token_hex(4)+'@smproject.site',
       'RAG_TEST_PASSWORD':secrets.token_urlsafe(32),'RAG_TEST_TENANT_ID':str(uuid.uuid4())}
 fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:
  for k,v in data.items():f.write(f'{k}={v}\n')
payload={'email':data['RAG_TEST_EMAIL'],'password':data['RAG_TEST_PASSWORD'],'tenant_id':data['RAG_TEST_TENANT_ID']}
endpoint='/api/v1/auth/login' if (OUT/'test-principal.json').exists() else '/api/v1/auth/register'
req=Request(data['RAG_BASE_URL']+endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Run-Id':'server-observation-deployment'})
with urlopen(req,timeout=15) as response:
 body=json.load(response)
assert body['code']==0
user=body['data']['user']
(OUT/'test-principal.json').write_text(json.dumps({'user_id':user['id'],'tenant_id':user['tenant_id'],'email':user['email'],'role':user['role'],'purpose':'server-observation and remote load testing only'},ensure_ascii=False,indent=2))
token=body['data']['access_token']
for path in ['/api/v1/auth/me','/api/v1/tasks','/api/v1/reports']:
 req=Request(data['RAG_BASE_URL']+path,headers={'Authorization':'Bearer '+token,'X-Run-Id':'server-observation-deployment'})
 with urlopen(req,timeout=15) as response:
  assert response.status==200
  print(path+': HTTP 200')
print('Dedicated test principal ready; credentials saved with mode 0600; no model call.')
