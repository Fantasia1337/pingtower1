import os
import sys
from pathlib import Path

# ensure app import
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# use sqlite DB file inside MAINPROJECT
os.environ.setdefault('DB_URL', f'sqlite+pysqlite:///{(ROOT / "data.sqlite").as_posix()}')

from fastapi.testclient import TestClient
from app.db.init_db import main as init_db
from app.main import app


def run():
	init_db()
	client = TestClient(app)
	# health
	r = client.get('/health')
	assert r.status_code == 200 and r.json().get('status') == 'ok'
	# create service
	payload = {"name":"Site A","url":"https://example.com","interval_s":60,"timeout_s":5}
	r = client.post('/services', json=payload)
	assert r.status_code == 201, r.text
	service = r.json()
	# list services
	r = client.get('/services')
	assert r.status_code == 200 and any(s['id']==service['id'] for s in r.json())
	# status placeholder
	r = client.get(f"/status/{service['id']}")
	assert r.status_code == 200 and 'ok' in r.json()
	# history
	r = client.get(f"/services/{service['id']}/history?limit=10")
	assert r.status_code == 200
	# recheck enqueues
	r = client.post(f"/services/{service['id']}/recheck")
	assert r.status_code == 202 and r.json().get('queued') is True
	print('SMOKE OK')


if __name__ == '__main__':
	run() 