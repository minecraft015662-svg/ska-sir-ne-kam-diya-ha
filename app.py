from flask import Flask, render_template, request, jsonify
from core.provision import create_vps_container

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('vps.html')

@app.route('/vps/create', methods=['POST'])
def create_vps():
    vps_name = request.form.get('vps_name')
    root_password = request.form.get('root_password')
    result = create_vps_container(vps_name, root_password=root_password)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
