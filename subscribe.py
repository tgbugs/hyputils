#!/usr/bin/env python3.5

import asyncio
import certifi
import websockets
import ssl
import uuid
import json
from IPython import embed


def _ssl_context(verify=True):
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    if not verify:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


async def setup_connection(websocket):
    message = {'messageType': 'client_id',
               'value': str(uuid.uuid4()),}
    print('SETUP MESSAGE', message)
    await websocket.send(json.dumps(message))


async def setup_filters(websocket, filters):
    print('SETUP FILTERS', filters)
    await websocket.send(json.dumps(filters))


async def process_messages(websocket, handler):
    while True:
        response = await websocket.recv()
        try:
            msg = json.loads(response)
        except ValueError:
            pass
        if msg:
            handler.process(msg)
        else:
            pass


class Handler:
    def __init__(self, post_filter_rules):
        pass

    def process(self, message):
        if message['type'] == 'annotation-notification':
            print('ANNOTATION')
            print(message)
        else:
            print('NOT ANNOTATION')
            print(message)


async def ws_loop():
    websocket_endpoint = 'wss://hypothes.is/ws'
    post_filter_rules = None
    handler = Handler(post_filter_rules)
    ssl_context = _ssl_context(verify=True)
    filters = {'filter': {
        'match_policy': 'include_all',
        'clauses': [],
        'actions': {'create': True, 'update': True, 'delete': True},
        }
    }

    while True:
        try:
            async with websockets.connect(websocket_endpoint, ssl=ssl_context) as ws:
                await setup_connection(ws)
                print('working!')
                await setup_filters(ws, filters)
                print('subscribed')
                await process_messages(ws, handler)
        except KeyboardInterrupt:
            break
        except websockets.exceptions.ConnectionClosed:
            pass

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(ws_loop())

if __name__ == '__main__':
    main()

