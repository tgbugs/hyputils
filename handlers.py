"""
    Implementation of various filter/handler pairs.
"""
import os
import yaml
from zdesk import Zendesk


class filterHandler:
    """ Base class that all filter handlers should be derived from.
        Any authenticiation state needed to link services should be
        managed in __init__. Sorta a crappy python ITTT.
    """

    def filter(self, message):
        return True

    def handler(self, message):
        raise NotImplemented('You need to implement this in a subclass')

    def __call__(self, message):
        if self.filter(message):
            self.handler(message)


class slackHandler:
    def __init__(self, api_token):
        self.api_token = api_token
    
    def filter(self):
        pass

    def handler(self):
        pass


class zendeskHandler(filterHandler):
    """ Handler that creates zendeks tickets. Currently hardcoding filter
        rules (eg uri) but could make this configurabe if desired. May also
        break these filterHandlers out into their own file that users could
        create independently of the subscription setup here....
    """

    def __init__(self, infopath='~/files/zendeskinfo.yaml'):
        with open(os.path.expanduser(infopath), 'rt') as f:
            self.zendeskinfo = yaml.load(f)
        self.zendesk = Zendesk(**self.zendeskinfo)

    def filter(self, message):
        if message['options']['action'] != 'create':
            print('Annotation was not a creation, run update path?')
            return
        data = message['payload'][0]
        if 'scicrunch.org' in data['uri']:
            return True

    def handler(self, message):
        data = message['payload'][0]
        exact = [i['exact'] for o in data['target'] for i in o['selector'] if 'selector' in o and 'exact' in i]
        exact = exact[0] if exact else 'No description provided'
        href = data['links']['incontext']
        new_ticket = {                                 
            'ticket': {
                'requester': {
                    'name': 'hypothesis bot',
                    'email': self.zendeskinfo['zdesk_email'],
                },
                'subject':'hypothes.is annotation on {} by {}'.format(data['document']['title'], data['user'].split(':',1)[1]),
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
        result = self.zendesk.ticket_create(data=new_ticket)
        print(result)


class printHandler(filterHandler):
    def filter(self, message):
        return True

    def handler(self, message):
        print(message['payload'][0]['links']['incontext'])
        print(message)


def getFilterHandlers():
    return [zendeskHandler(), printHandler()]  # order matters

