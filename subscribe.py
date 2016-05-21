#!/usr/bin/env python3.5

import os
from os import environ
import asyncio
import ssl
import uuid
import json

import certifi
import websockets
import robobrowser
from zdesk import Zendesk

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


def generic_incontext_handler(message):
    return message['payload'][0]['links']['incontext']


def slack_handler(message):
    pass


class slackHandler:
    def __init__(self, api_token):
        self.api_token = api_token
    
    def connect(self):
        pass


# zendesk
with open(os.path.expanduser('~/files/zendeskinfo.json'), 'rt') as f:
    zendeskinfo = json.load(f)
zendesk = Zendesk(**zendeskinfo)

def zdesk_handler(message):
    data = message['payload'][0]
    #exact = data['target'][0]['selector'][3]['exact']
    exact = [i['exact'] for o in data['target'] for i in o['selector'] if 'exact' in i][0]
    href = data['links']['incontext']
    new_ticket = {                                 
        'ticket': {
            'requester': {
                'name': 'hypothesis bot',
                'email': zendeskinfo['zdesk_email'],
            },
            'subject':'hypothes.is annotation on {} by {}'.format(data['title'], data['user'].split(':',1)[1]),
            'description': '"{}" | {} {}'.format(exact, data['text'], href) , 
            'tags': data['tags'],
            #'ticket_field_entries': [
                #{
                    #'ticket_field_id':24394906,  # referrer
                    #'value': 'hypothes.is {}'.format(data['user'].split(':',1)[1])  # hypothes.is
                #},
                #{
                    #'ticket_field_id':24394926,  # url
                    #'ticket_field_id':'Url',  # url
                    #'value': data['links']['incontext']  # incontext_url
                #}
            #]
        }
    }
    result = zendesk.ticket_create(data=new_ticket)
    print(result)


class Handler:
    def __init__(self, post_filter_rules):
        pass

    def process(self, message):
        if message['type'] == 'annotation-notification':
            print('ANNOTATION')
            #print(generic_incontext_handler(message))
            zdesk_handler(message)
            print(message)
            print()
        else:
            print('NOT ANNOTATION')
            print(message)

        #embed()


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
        self.uris = uris
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


async def ws_loop():
    websocket_endpoint = 'wss://hypothes.is/ws'
    post_filter_rules = None
    handler = Handler(post_filter_rules)
    ssl_context = _ssl_context(verify=True)
    
    #post to login form
    #requests.post(username passworld) response has a cookies
    #copy the set cookie header into the connect
    username = environ.get('HYPUSH_USERNAME', 'USERNAME')
    password = environ.get('HYPUSH_PASSWORD', 'PASSWORD')
    api_token = environ.get('HYPUSH_API_TOKEN', 'TOKEN')
    groups = environ.get('HYPUSH_GROUPS', '__world__').split(' ')
    print(groups)

    #headers = {'Authorization': 'Bearer ' + api_token} #, 'Content-Type': 'application/json;charset=utf-8' }  # once the websocket auth goes in
    header = get_auth_header(username, password)
    extra_headers = {

    }
    extra_headers.update(header)
    filters = preFilter(groups=groups).export()
        #uris=['https://github.com/','https://hypothes.is/'],
        #uris=['https://knowledge-space.org/'],
        #groups=['__world__']).export()

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
        except websockets.exceptions.ConnectionClosed:
            pass

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(ws_loop())

if __name__ == '__main__':
    main()

