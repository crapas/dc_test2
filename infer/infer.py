import os
import torch
import torch.nn as nn
from torchvision.transforms import transforms
from PIL import Image
from io import BytesIO
import requests
import logging
# 도커 컴포즈(2)를 위한 추가
import argparse
import time
# 추가 끝

from flask import Flask, request, jsonify
import sys

def init():
    # 도커 컴포즈(2)를 위한 추가
    # 명령행에서 --port, --model_key 옵션으로 값을 받아옴
    parser = argparse.ArgumentParser(description="Infer service for flyai tutorial")
    parser.add_argument('--port', '-p', type=int, default=5001, help='Port number (default: 5001)')
    parser.add_argument('--model_key', '-m', type=str, required=False, help='model key')

    args = parser.parse_args()
    # port는 init 함수 밖에서 사용하기 때문에 global로 지정
    global service_port
    service_port = args.port
    # 추가 끝

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    lib_path = os.environ.get('LIBPATH')
    global model
    if lib_path is None:
        lib_path = '../lib/'

    sys.path.append(lib_path)
    from digit_recognizer import DigitRecognizer
    model = DigitRecognizer()

    model_path = os.environ.get('MODELPATH')    
    if model_path is None:
        logging.warning("MODELPATH is not defined. Default value will be used.")                      
        model_path = '../model/'                
    


    # 도커 컴포즈(2)를 위한 수정. 
    # 기존의 MODELURL 대신 MODELHOST와 MODELENDPOINT를 사용하며
    # model_key 파라미터를 추가로 전달합니다.
    # 그리고 model_service가 살아 있는지 확인합니다. 이를 위해서 MSTIMEOUT 환경변수도 사용합니다.
    # 또한 model download 실패시 반복 횟수를 지정하기 위한 MODELGETRETRY 환경변수도 사용합니다.

    #model_url = os.environ.get("MODELURL")    
    #if model_url is None:
    #    logging.warning("MODELURL is not defined. Default value will be used.")                      
    #    model_url = "http://localhost:5002/model"

    model_get_retry_str = os.environ.get("MODELGETRETRY")
    if model_get_retry_str is None:
        model_get_retry = 5
    else:
        model_get_retry = int(model_get_retry_str)

    modelservice_host = os.environ.get('MSHOST')
    modelservice_port = os.environ.get('MSPORT')
    modelservice_endpoint = os.environ.get('MSENDPOINT')
    ms_timeout_str = os.environ.get('MSTIMEOUT')
    if modelservice_host and modelservice_port and modelservice_endpoint:
        model_url = f"http://{modelservice_host}:{modelservice_port}{modelservice_endpoint}"
        health_check_url = f"http://{modelservice_host}:{modelservice_port}/"
    else:
        model_url = "http://localhost:5002/model"
        health_check_url = "http://localhost:5002/"
    
    logging.info(f"model url : {model_url}")
    # 옵션에 model_key가 포함되어 있으면 url에 쿼리를 추가합니다.
    if args.model_key:
        model_url += f"?model_key={args.model_key}"

    # MSTIMEOUT 환경변수가 있을 때만 확인
    # 오류 발생 시 1초마다 재확인해서, 시간이 다 되면 종료
    if ms_timeout_str is not None:        
        logging.info("Checking model_service is alive")
        alive = False
        for i in range(int(ms_timeout_str)):
            try:
                response = requests.get(health_check_url)
                response.raise_for_status()
                logging.info("model_service is alive")
                alive = True
                break
            except:
                logging.error(f"Error occured while model_service_health check ({i + 1}/{int(ms_timeout_str)})")
                time.sleep(1)
        if alive == False:
            logging.critical("Model_service seems inactive, so exit.")
            exit(-1)
    else:
        logging.info("MSTIMEOUT is not setted, so skippiing model_service is alive")
    # 수정 끝

    try:
        # 도커 컴포즈(2)를 위한 수정
        # model download에 실패했을 때 MODELGETRETRY에 지정한 횟수 만큼 반복하고 그래도 실패하면 종료

        model_download_trial = 0
        while True:
            response = requests.get(model_url)
            if response.status_code == 200:
                model_bytes = response.content
                break
            # redis RESTAPI를 사용할 수 있는데 modelfile을 얻어올 수 없으면 종료
            else:
                model_download_trial += 1
                if model_download_trial == model_get_retry:
                    logging.critical('Modelservice seems active, but modelfile is not provided. Inferservice is shutdowned.')
                    exit(-1)
                else:
                    logging.error(f"Model download failed. Retry ({model_download_trial}/{model_get_retry})")
                    time.sleep(1)
        # 수정 끝
        
        model.load_state_dict(torch.load(BytesIO(model_bytes)))
        logging.info("Model is loaded successfully from redis server.")
    except Exception as e:
        # redis를 RESTAPI를 사용할 수 없으면 model/modelfile 파일을 읽어옴
        logging.warning("Modelservice seems inactive, so model will be loaded from file.")
        try:
            model.load_state_dict(torch.load(model_path + 'modelfile')) 
            logging.info("Model is loaded successfully from file.")
        except Exception as e:
            logging.critical("Failed to load model from file. Inferservice is shutdowned.")
            exit(-1)

    model.eval()

def infer(image_file):
    try:
        transform = transforms.Compose([transforms.Grayscale(), transforms.ToTensor()])

        image = Image.open(image_file).convert('L')     
        image = transform(image).unsqueeze(0)           

        # 추론
        with torch.no_grad():                           
            output = model(image)                       

        # 결과 출력
        _, predicted = torch.max(output, 1)             
        return None, predicted.item()
    except Exception as e:                              
        return e, -1

init()
app = Flask(__name__)

@app.route('/', methods=['GET'])
def i_am_alive():
    return "infer service is alive", 200

@app.route('/recognize', methods=['POST'])          
def recog_image():                                  
    if 'image' not in request.files:                
        return "No image file uploaded", 400        
    image_file = request.files['image']             
    e, result = infer(image_file)
    if e == None:
        return jsonify({'result':result})     
    else:
        return f"Error recognizing image: {str(e)}", 500


if __name__ == '__main__':
    # 도커 컴포즈(2)를 위한 수정. 
    # --port로 추가한 port를 사용합니다.  
    app.run(host='0.0.0.0', port=service_port)
    # 수정 끝                   
