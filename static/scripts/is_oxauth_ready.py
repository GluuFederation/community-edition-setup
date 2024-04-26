#!/usr/bin/python3

import json
import time
import http.client

for _ in range(20):
    try:
        conn = http.client.HTTPConnection('localhost', 8081)
        conn.request("GET", "/oxauth/.well-known/openid-configuration")
        response = conn.getresponse()
        text = response.read()
        openid_config = json.loads(text.decode())
        break
    except:
        time.sleep(2)
