"""Smoke tests for protected website and asynchronous YouTube import flow."""
import base64
import os
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app as service


class WebDeploymentTests(unittest.TestCase):
    def test_website_password_and_health(self):
        with patch.object(service, 'ACCESS_PASSWORD', 'secret123'):
            with TestClient(service.app) as client:
                self.assertEqual(client.get('/').status_code, 401)
                self.assertEqual(client.get('/static/app.js').status_code, 401)
                self.assertEqual(client.get('/api/health').status_code, 200)
                token = base64.b64encode(b'clipforge:secret123').decode('ascii')
                auth = {'Authorization': 'Basic '+token}
                r=client.get('/', headers=auth)
                self.assertEqual(r.status_code, 200)
                self.assertIn('Versi website', r.text)
                self.assertIn('no-store',client.get('/api/health').headers['cache-control'])
                self.assertEqual(client.get('/static/site.webmanifest',headers=auth).status_code, 200)

    def test_import_is_background_job(self):
        source = {'id':'test123', 'title':'Contoh','duration':90,'width':1280,'height':720,'origin':'youtube','heatmap_available':False}
        with patch.object(service,'ACCESS_PASSWORD',''), patch.object(service,'import_youtube',return_value=source):
            with TestClient(service.app) as client:
                r=client.post('/api/imports/youtube',json={'url':'https://youtu.be/AbcD1234EFG','have_rights':True})
                self.assertEqual(r.status_code,200,r.text)
                import_id=r.json()['import_id']
                for _ in range(40):
                    state=client.get('/api/imports/'+import_id).json()
                    if state['status']!='queued' and state['status']!='processing':break
                    time.sleep(.02)
                self.assertEqual(state['status'],'done',state)
                self.assertEqual(state['source']['id'],'test123')
                invalid=client.post('/api/imports/youtube',json={'url':'https://bad.example/v','have_rights':True})
                self.assertEqual(invalid.status_code,400)
                forbidden=client.post('/api/imports/youtube',json={'url':'https://youtu.be/AbcD1234EFG','have_rights':False})
                self.assertEqual(forbidden.status_code,400)

if __name__ == '__main__': unittest.main()
