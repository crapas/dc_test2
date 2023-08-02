import flask
from flask import Flask, request, jsonify
import io
import os
import redis
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# variables for redis connect
redis_host = os.environ.get('REDISHOST')
if redis_host is None:
    logging.warning("REDISHOST is not defined. Default value will be used.")
    redis_host = "localhost"    

redis_port_str = os.environ.get('REDISPORT')
if redis_port_str is None:
    logging.warning("REDISPORT is not defined. Default value will be used.")
    redis_port = 6379
else:
    try:
        redis_port = int(redis_port_str)
    except ValueError:
        logging.critical("ENV REDISPORT is not valid")
        exit -1

# 도커 컴포즈(2)를 위한 수정
# RSTIMEOUT에 설정된 값을 기준으로, 이 시간 이상 redis 서버가 응답이 없으면 종료
rs_timeout_str = os.environ.get('RSTIMEOUT')
if rs_timeout_str is not None:
    logging.info("Checking REDIS Availability")
    try:
        redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=0, socket_timeout=int(rs_timeout_str))
        ping_response = redis_client.ping()
        if ping_response != b'PONG':
            logging.critical("Error occured while cheking redis available")
            exit -1
        logging.info("Found REDIS available")
    except Exception as e:
        logging.critical(f"Error occured while cheking redis available - {e}")
else:
    logging.info("$RSTIMEOUT is not defined.")
# 수정 끝
    



model_key = os.environ.get('MODELKEY')
if model_key is None:
    logging.warning("MODELKEY is not defined. Default value will be used.")
    model_key = "modelfile"

# 환경변수 MODELPATH, MODELFILE이 존재하고, MODELPATH/MODELFILE이 존재할 때
# 서비스를 시작할 때 이를 redis에 save
model_path = os.environ.get('MODELPATH')
model_file = os.environ.get('MODELFILE')
if model_path is not None and model_file is not None:
    model_file_path = os.path.join(model_path, model_file)
    if os.path.isfile(model_file_path):
        with open(model_file_path, 'rb') as file:
            model_data = file.read()
        try:
            redis_client.set(model_key, model_data)
            logging.info("Modelfile is uploaded succefully at starting.")
        except Exception as e:
            logging.error("Modelfile can't be uploaded for server issue. Check redis server")

    else:
        logging.error("$MODELPATH and $MODELFILE exist, but $MODELPATH/$MODELFILE isn't valid file, so modelfile cannot be uploaded at starting.")
else:
    logging.warning("$MODELPATH and(or) $MODELFILE don't exist, so modelfile cannot be uploaded at starting")

app = Flask(__name__)


@app.route('/model', methods=['POST'])
def upload_model():
    if 'modelfile' not in request.files:
        logging.error("No model file in request")
        return "No model file uploaded", 400
    
    # 도커 컴포즈(2)를 위한 추가
    # model_key 파라미터를 확인하고, 해당 파라미터가 없으면 기본값(model_key)를 사용
    upload_model_key = request.form.get('model_key', model_key)
    # 추가 끝

    try:
        model_file = request.files['modelfile'].read()

        # 도커 컴포즈(2)를 위한 수정
        # redis 저장 키를 기존의 model_key에서 upload_model_key로 변경
        redis_client.set(upload_model_key, model_file)
        # 수정 끝

        return jsonify({'result':200})
    except Exception as e:
        logging.error('Cannot upload modelfile. Check redis server')
        return f"Error upload modelfile: {str(e)}", 500


@app.route('/model', methods=['GET'])
def send_model():

    # 도커 컴포즈(2)를 위한 추가
    # query parameter model_key 확인하고, 해당되는 파라미터가 있으면 이 파라미터를 사용
    # 없으면 기본 값을 사용
    requested_model = request.args.get('model_key')
    if requested_model == None:
        requested_model = model_key
    # 추가 끝

    try:
        model_file_data = redis_client.get(requested_model)
        if model_file_data is None:
            return "Modelfile not found in redis server", 404
        model_file = io.BytesIO(model_file_data)
        logging.info("Modelfile will be sent.")
        return flask.send_file(model_file, download_name='modelfile.server', as_attachment=False)
    except Exception as e:
        logging.error('There are some errors.')
        flask.abort(404, 'Modelfile is not provided from redis server')

if __name__ == '__main__':      
    app.run(host='0.0.0.0', port=5002)                
