"""Test-only WSGI bridge over stdio; never registered in the running application.

Allows browser integration testing where the sandbox blocks loopback sockets.
The isolated app injects test identities/extraction, and deletes its database on exit.
"""
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_api import ApiTests, pdf_bytes
from backend.processing import process_one
from backend.initial_analysis import process_initial_one

case = ApiTests()
case.setUp()
case.app.config['REVIEW_ANALYZER'] = lambda context, documents, config: {
    'analysis': {'summary': 'Analisis fiktif: cocokkan kembali total dan rekening dengan PDF.', 'risk': 'MEDIUM',
                 'findings': [{'severity': 'WARNING', 'field': 'total_amount', 'observation': 'Periksa nilai pada PDF.',
                               'recommendation': 'Bandingkan seluruh baris sebelum menyetujui.'}],
                 'next_steps': ['Periksa PDF asli.', 'Simpan koreksi bila diperlukan.']}, 'model': 'fixture-only'}
case.app.config['INITIAL_ANALYZER']=case.app.config['REVIEW_ANALYZER']
case.app.config['AGENT_RESPONDER']=lambda q,c,h,k:{'answer':'Fixture asisten '+c['role']+': hasil pemeriksaan tersimpan untuk '+str(c.get('selected_request',{}).get('id','ringkasan pekerjaan'))+'.',
    'next_steps':['Periksa hasil pada dokumen.'],'intent':'PREVIEW_TELEGRAM' if c['role']=='reviewer' else 'ANSWER'}
case.app.config.update(TELEGRAM_BOT_TOKEN='',TELEGRAM_BOT_USERNAME='amiga_fixture_bot')
telegram_updates=[];telegram_sent=[]
def telegram_fixture(method,payload,pdf):
    if method=='getUpdates':return [e for e in telegram_updates if e['update_id']>=payload.get('offset',0)]
    if method=='getMe':return {'username':'amiga_fixture_bot'}
    telegram_sent.append({'method':method,'payload':payload,'has_pdf':bool(pdf)})
    return {'message_id':len(telegram_sent)}
case.app.config['TELEGRAM_TRANSPORT']=telegram_fixture
setup_token = None
if os.environ.get('AMIGA_BROWSER_AUTH') == 'local_password':
    from backend.models import LocalCredential, User, Role
    from backend.local_auth import hash_password, prepare_owner_setup
    from sqlalchemy import select, delete
    case.app.config.update(AUTH_METHOD='local_password', GOOGLE_CLIENT_ID='', ADMIN_BOOTSTRAP_EMAIL='admin@example.test')
    encoded = hash_password('Fictional-AMIGA-Password!')
    with case.app.extensions['amiga_db'].begin() as db:
        for user in db.scalars(select(User)):
            if user.id == 'admin':
                user.account_status = 'PENDING_ADMIN'
                continue
            db.add(LocalCredential(user_id=user.id, password_hash=encoded))
        db.execute(delete(Role).where(Role.user_id=='admin', Role.role=='SYSTEM_ADMIN'))
    setup_token = prepare_owner_setup(case.app)
case.claims['pending-admin'] = {**case.claims['owner'], 'sub': 'pending-admin-sub', 'email': 'pending@example.test'}
client = case.app.test_client(use_cookies=False)
qa = Path('.runtime-temp/browser-qa')
qa.mkdir(parents=True, exist_ok=True)
(qa / 'invoice.pdf').write_bytes(pdf_bytes('Invoice fiktif browser QA'))
(qa / 'evidence.pdf').write_bytes(pdf_bytes('Bukti fiktif browser QA'))
from PIL import Image, ImageDraw
photo=Image.new('RGB',(600,800),'white')
ImageDraw.Draw(photo).text((40,40),'INVOICE FIKTIF - QA FOTO',fill='black')
photo.save(qa/'invoice-photo.png')
print(json.dumps({'ready': True, 'setup_token': setup_token}), flush=True)
try:
    for line in sys.stdin:
        command = json.loads(line)
        if command.get('fixture_telegram_enable'):
            case.app.config['TELEGRAM_BOT_TOKEN']='fixture-only-token'
            print(json.dumps({'id':command['id'],'fixture':True}),flush=True);continue
        if command.get('fixture_telegram_start'):
            telegram_updates.append({'update_id':len(telegram_updates)+1,'message':{'text':'/start '+command['fixture_telegram_start'],
                'chat':{'type':'private','id':123456},'from':{'id':123456,'username':'fictional_uploader'}}})
            print(json.dumps({'id':command['id'],'fixture':True}),flush=True);continue
        url = urlparse(command['url'])
        try:
            response = client.open(url.path + ('?' + url.query if url.query else ''),
                method=command['method'], headers=command.get('headers', {}),
                data=base64.b64decode(command.get('body') or ''), base_url='http://127.0.0.1:53919')
            if command['method'] == 'POST' and (url.path == '/api/requests' or url.path.endswith('/document-revision')) and response.status_code == 201:
                process_one(case.app, response.json['data']['id'])
            if command['method'] in ('POST','PATCH') and response.status_code<300:
                while process_initial_one(case.app):pass
            content = response.get_data()
            headers = {k: v for k, v in response.headers if k.lower() not in ('content-length', 'transfer-encoding')}
            result = {'id': command['id'], 'status': response.status_code, 'headers': headers,
                      'body': base64.b64encode(content).decode('ascii')}
            response.close()
        except Exception as exc:
            result = {'id': command['id'], 'error': str(exc)}
        print(json.dumps(result), flush=True)
finally:
    case.tearDown()
