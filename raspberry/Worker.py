#!/usr/bin/python3
import asyncio
import websockets
import threading
import cv2
import base64
import json
import numpy as np
import time
from ArduinoComm import ArduinoComm
import os

VIDEO_HOSTNAME = "0.0.0.0"
VIDEO_PORT = 8888

ARDUINO_HOSTNAME = "0.0.0.0"
ARDUINO_PORT = 7777

CONFIG_PATH = "./Object_Detection_Files/ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt"
WEIGHT_PATH = "./Object_Detection_Files/frozen_inference_graph.pb"

cap = cv2.VideoCapture(0)
cap.set(3, 480)
cap.set(4, 480)



class VideoWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.loop = asyncio.get_event_loop()
        self.cap = cap
        self.SEND_DELAY = 0.1
        self.recv_img_queue = []
        self.websockets = []


    def run(self):
        while True:
            if len(self.websockets):
                ret, img = self.cap.read()
                if ret:
                    ret, img = cv2.imencode('.png', img)
                    if ret:
                        res = base64.b64encode(img).decode()
                        try:
                            coro = self.websockets[-1].send(json.dumps({'image':res}))
                            future = asyncio.run_coroutine_threadsafe(coro, video_loop)
                        except:
                            pass
                        time.sleep(self.SEND_DELAY)


    async def handler(self, websocket, path):
        self.websockets.append(websocket)
        while True:
            try:
                data = await websocket.recv()
                img = base64.b64decode(json.loads(data)["image"].split("base64,")[1])
                cc = cv2.imdecode(np.frombuffer(img, np.int8), cv2.IMREAD_COLOR)
                cv2.namedWindow("video", cv2.WND_PROP_FULLSCREEN)          
                cv2.setWindowProperty("video", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                cv2.imshow('video', cc)
                cv2.waitKey(1)


            except websockets.exceptions.ConnectionClosed:
                print("Video Socket Closed")
                break

            except Exception as e:
                print(e)
                break
        self.websockets.pop(self.websockets.index(websocket))


class ArduinoWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.loop = asyncio.get_event_loop()
        self.cap = cap
        self.websockets = []
        self.arduino_comm = ArduinoComm("/dev/ttyACM0")

        self.comm_flags = {"auto_move": False}
        self.commands = {
            'auto_forward': b'1',
            'auto_backward': b'2',
            'manual_forward': b'8',
            'manual_backward': b'9',
            'left': b'3',
            'right': b'4',
            'stop':  b'5',
            'shoot': b'6',
            'shoot_stop': b'7'
        }

        self.classNames = []
        classFile = "./Object_Detection_Files/coco.names"
        with open(classFile, "rt") as f:
            self.classNames = f.read().rstrip("\n").split("\n")

        self.net = cv2.dnn_DetectionModel(WEIGHT_PATH, CONFIG_PATH)
        self.net.setInputSize(480, 480)
        self.net.setInputScale(1.0/ 127.5)
        self.net.setInputMean((127.5, 127.5, 127.5))
        self.net.setInputSwapRB(True)


    def send_to_arduino(self, data):
        if isinstance(data, bytes):
            data = chr(int(data))
        self.arduino_comm.send(data)

    def getObjects(self, img, thres, nms, objects=[]):
        classIds, confs, bbox = self.net.detect(img, confThreshold=thres, nmsThreshold=nms)
        
        if len(objects) == 0: objects = self.classNames

        if len(classIds) != 0:
            for classId, confidence, box in zip(classIds.flatten(), confs.flatten(), bbox):
                className = self.classNames[classId - 1]
                if className in objects:
                    return box
        return []


    def run(self):
        while True:
            if self.comm_flags["auto_move"] == True:
                success, img = self.cap.read()            
                dog_coordinate = self.getObjects(img, 0.5, 0.25, objects=['dog'])

                if len(dog_coordinate) != 0:
                    centerx = dog_coordinate[0]
                    deg_degree = np.interp(centerx, [0, 480], [0, 180])
                    error = 20 // 2
                    print("deg_degree: %d" % deg_degree)
                    
                    # deg with error=10: 80 < deg < 100 <- don't move
                    if deg_degree > 90+error:
                        print("auto left")
                        self.send_to_arduino(self.commands['left'])
                        self.send_to_arduino(self.commands['stop'])
                    elif deg_degree < 90-error:
                        print("auto right")
                        self.send_to_arduino(self.commands['right'])
                        self.send_to_arduino(self.commands['stop'])
                    else:
                        pass
                #else:
                #    print("Not found")
                #time.sleep(0.3)
            else:
                time.sleep(1)


    async def handler(self, websocket, path):
        self.websockets.append(websocket)
        while True:
            try:
                data = await websocket.recv()
                data = json.loads(data)
                
                print("RECV COMMAND: %d" % data["number"])
                if int(data["number"]) == 8: # set auto move
                    self.comm_flags["auto_move"] = not self.comm_flags["auto_move"]
                    cmd = 10 + (self.comm_flags["auto_move"] == False)
                else:
                    cmd = data["number"]
                    if data["number"] == 1:
                        cmd = self.commands["manual_forward"]
                    if data["number"] == 2:
                        cmd = self.commands["manual_backward"]

                print("to_comm", cmd)
                self.arduino_comm.send(chr(int(cmd)).encode())
                
            except websockets.exceptions.ConnectionClosed:
                print("Video Socket Closed")
                break

            except Exception as e:
                print(e)
                break

        self.websockets.pop(self.websockets.index(websocket))


if __name__ == '__main__':
    arduino_worker = ArduinoWorker()
    arduino_server = websockets.serve(arduino_worker.handler, ARDUINO_HOSTNAME, ARDUINO_PORT)
    arduino_worker.start()
    

    videoworker = VideoWorker()
    video_server = websockets.serve(videoworker.handler, VIDEO_HOSTNAME, VIDEO_PORT)
    videoworker.start()

    arduino_loop = asyncio.get_event_loop()
    arduino_loop.run_until_complete(arduino_server)
    
    video_loop = asyncio.get_event_loop()
    video_loop.run_until_complete(video_server)

    arduino_loop.run_forever()
    video_loop.run_forever()


    
