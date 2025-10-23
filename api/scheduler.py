import requests
REGION_ENDPOINTS = {
  'ashburn': 'http://agent:8080',
  'dallas':  'http://agent:8080'
}

def place_job(job_id: str, region: str, spec: dict) -> dict:
    ep = REGION_ENDPOINTS[region]
    r = requests.post(f"{ep}/submit", json={
      'job_id': job_id,
      'image': spec['image'],
      'cmd': spec['cmd'],
      'gpus': spec['gpus'],
      'gpu_model': spec['gpu_model']
    }, timeout=5)
    r.raise_for_status()
    return r.json()
