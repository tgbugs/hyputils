#!/usr/bin/env python3.7
"""
Usage:
    test <name>
"""

# WS client example

import asyncio
import websockets
from docopt import docopt
args = docopt(__doc__)
name = args['<name>']


async def hello():
    async with websockets.connect('ws://localhost:5050') as websocket:
        await websocket.send(name)
        print(f"> {name}")

        greeting = await websocket.recv()
        print(f"< {greeting}")
        while True:
            print('waiting for next message')
            print(await websocket.recv())


asyncio.get_event_loop().run_until_complete(hello())
