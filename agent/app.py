from flask import Flask, request, jsonify
app = Flask(__name__)

@app.post('/submit')
def submit():
    j = request.get_json()
    # TODO: bridge to local K8s cluster; here we just accept and fake ETA
    return jsonify({'accepted': True, 'eta_minutes': 10})

@app.get('/')
def ok():
    return 'agent ok', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
