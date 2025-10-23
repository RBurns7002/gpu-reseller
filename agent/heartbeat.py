import os, time, requests

API = os.environ.get('API', 'http://localhost:8000')
REGION = os.environ.get('REGION', 'dallas')

session = requests.Session()
session.headers.update({'User-Agent': 'gpu-agent/1.0'})

def register_with_backoff(max_wait: int = 60):
    wait = 1
    while True:
        try:
            resp = session.post(
                f"{API}/v1/agents/register",
                json={
                    'region_code': REGION,
                    'agent_name': f'{REGION}-agent-1',
                    'meta': {'k8s': 'v1.30'}
                },
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            return data['agent_id'], data['agent_api_key']
        except Exception as e:
            print(f"register failed: {e}; retrying in {wait}s")
            time.sleep(wait)
            wait = min(max_wait, wait * 2)

agent_id, api_key = register_with_backoff()
headers = {'X-Agent-Key': api_key}

while True:
    try:
        metrics = {'total_gpus': 10, 'free_gpus': 6, 'utilization': 0.4}
        nodes = [{
            'hostname': f'{REGION}-node-{i}',
            'gpu_model': 'DGX Spark',
            'gpus': 1,
            'vram_gb': 128,
            'state': 'ready',
            'labels': {}
        } for i in range(10)]
        r = session.post(
            f"{API}/v1/agents/heartbeat",
            headers=headers,
            json={'agent_id': agent_id, 'metrics': metrics, 'nodes': nodes},
            timeout=5,
        )
        print('hb', r.status_code)
    except Exception as e:
        print(f"heartbeat failed: {e}")
    time.sleep(10)
