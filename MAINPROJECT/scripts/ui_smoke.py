import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app


def run():
	c = TestClient(app)
	# index.html
	r = c.get('/')
	assert r.status_code == 200 and 'text/html' in r.headers.get('content-type','')
	assert b'PingTower' in r.content
	# incidents page
	r = c.get('/incidents-page')
	assert r.status_code == 200 and 'text/html' in r.headers.get('content-type','')
	# static assets
	for path in [
		'/static/style.css',
		'/static/js/app.js',
		'/static/js/api.js',
		'/static/js/notifications.js'
	]:
		res = c.get(path)
		assert res.status_code == 200
	print('UI_SMOKE OK')


if __name__ == '__main__':
	run() 