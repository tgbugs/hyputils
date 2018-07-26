#!/usr/bin/env python3.5

import os
import asyncio
import ssl
import uuid
import json
from os import environ
from threading import Thread

import certifi
import websockets
import robobrowser


class Handler:
    def __init__(self, filter_handlers):
        self.filter_handlers = filter_handlers  # list of filterHandlers that should be run on every message

    def process(self, message):
        if message['type'] == 'annotation-notification':
            for fh in self.filter_handlers:
                fh(message)
        else:
            print('NOT ANNOTATION')
            print(message)


class preFilter:
    """ Create a filter that will run on the hypothes.is server
        Make group empty to default to allow all groups the authed user
        is a member of in the hypothes.is system.
    """
    def __init__(self, groups=[], users=[], uris=[], tags=[],
                 create=True, update=True, delete=True,
                 match_policy='include_all'):

        self.create = create
        self.update = update
        self.delete = delete

        #include_all include_any
        self.match_policy = match_policy

        self.groups = groups
        self.users = users
        self.uris = uris  # NOTE: uri filters must be exact :(
        self.tags = tags

        self.clause_map = [
            ('/group', self.groups),  # __world__
            ('/users', self.users),
            ('/uri', self.uris),
            ('/tags', self.tags),
        ]

    def _make_clauses(self):
        clauses = []
        for field, value in self.clause_map:
            if value:
                clauses.append(
                    {'field':[field],
                     'case_sensitive':True,
                     'operator':'one_of',
                     'options':{},
                     'value':value,
                    }
                )

        return clauses

    def export(self):
        output = {
            'filter':{
                'actions':{
                    'create':self.create,
                    'update':self.update,
                    'delete':self.delete,
                },
                'match_policy':self.match_policy,
                'clauses':self._make_clauses(),
            },
        }

        return output


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


def get_auth_header(username, password):
    url = 'https://hypothes.is/login'
    br = robobrowser.RoboBrowser()
    br.open(url)
    form = br.get_form(id=0)
    print(form)
    form['username'].value = username
    form['password'].value = password
    br.submit_form(form)
    session_cookie = br.session.cookies['session']
    return {'Cookie': 'session=%s' % session_cookie}


def setup_websocket(api_token, filters, filter_handlers, websocket_endpoint='wss://hypothes.is/ws', extra_headers=None):
    if extra_headers is None:
        extra_headers = {}
    async def ws_loop():
        #websocket_endpoint = 'wss://hypothes.is/ws'
        #filter_handlers = getFilterHandlers()
        handler = Handler(filter_handlers)
        ssl_context = _ssl_context(verify=True)

        headers = {'Authorization': 'Bearer ' + api_token}
        extra_headers.update(headers)

        while True:
            try:
                async with websockets.connect(websocket_endpoint, ssl=ssl_context, extra_headers=extra_headers) as ws:
                    await setup_connection(ws)
                    print('working!')
                    await setup_filters(ws, filters)
                    print('subscribed')
                    await process_messages(ws, handler)
            except KeyboardInterrupt:
                break
            except (websockets.exceptions.ConnectionClosed, ConnectionResetError) as e:
                pass
    return ws_loop


class AnnotationStream:
    def __init__(self, annos, prefilter, *handler_classes, memoizer=None):
        from .hypothesis import api_token
        self.api_token = api_token
        self.annos = annos
        self.filters = prefilter
        self.filter_handlers = [handler(self.annos, memoizer=memoizer) for handler in handler_classes]

    @staticmethod
    def loop_target(loop, ws_loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ws_loop())

    def __call__(self):
        loop = asyncio.get_event_loop()
        ws_loop = setup_websocket(self.api_token, self.filters, self.filter_handlers)
        stream_loop = Thread(target=self.loop_target, args=(loop, ws_loop))
        return stream_loop 


def main():
    from handlers import getFilterHandlers
    loop = asyncio.get_event_loop()

    api_token = environ.get('HYPUSH_API_TOKEN', 'TOKEN')
    groups = environ.get('HYPUSH_GROUPS', '__world__').split(' ')
    filters = preFilter(groups=groups).export()
    filter_handlers = getFilterHandlers()
    print(groups)
    ws_loop, exit_val = setup_websocket(api_token, filters, filter_handlers)

    loop.run_until_complete(ws_loop())

if __name__ == '__main__':
    main()

