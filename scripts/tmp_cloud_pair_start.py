
from __future__ import annotations
import json
from urllib.request import Request, urlopen

api='http://106.55.62.122:8011'
project='e9548e5c-bb4a-4c58-94d6-a9fe658ce84d'
email='codex-cloud-verify@example.com'
password='password'

def req(path, method='GET', payload=None, token=''):
    data=None
    headers={'Accept':'application/json'}
    if token:
        headers['Authorization']='Bearer '+token
    if payload is not None:
        data=json.dumps(payload).encode('utf-8')
        headers['Content-Type']='application/json'
    r=Request(api+path, data=data, headers=headers, method=method)
    with urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))

session=req('/api/auth/session','POST',{'email':email,'password':password})['data']
token=session['access_token']
rot=req(f'/api/collaboration/projects/{project}/computer-nodes/cloud-server/pairing-token','POST',token=token)['data']
print(json.dumps({'token':rot.get('token'),'node':rot.get('computer_node_id')},ensure_ascii=False))
