"""Vision integration smoke tests; a training photograph is not accuracy validation."""
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.medicine import router, CLASS_NAMES

app = FastAPI()
app.include_router(router, prefix='/api')
client = TestClient(app)

def test_catalog_mapping():
    rows = client.get('/api/medicine/catalog').json()
    assert len(rows) == 20
    assert {row['id'] for row in rows} == set(CLASS_NAMES)
    assert len([row for row in rows if 'Escitalopram' in row['name']]) == 2

def test_image_errors():
    pytest.importorskip('tensorflow')
    assert client.post('/api/medicine/predict', content=b'x', headers={'content-type':'text/plain'}).status_code == 415
    assert client.post('/api/medicine/predict', content=b'x', headers={'content-type':'image/jpeg'}).status_code == 400
    assert client.post('/api/medicine/predict', content=b'x'*(10*1024*1024+1), headers={'content-type':'image/jpeg'}).status_code == 413

def test_model_reference_image():
    pytest.importorskip('tensorflow')
    root = Path(__file__).resolve().parents[2]
    raw = (root/'frontend/public/pharmacist/reference/00378-0208.jpg').read_bytes()
    response = client.post('/api/medicine/predict', content=raw, headers={'content-type':'image/jpeg'})
    assert response.status_code == 200
    data = response.json()
    assert data['verified'] is False
    assert len(data['candidates']) == 3
    assert data['candidates'][0]['id'] == '00378-0208'
    assert all(0 <= item['score'] <= 1 for item in data['candidates'])
