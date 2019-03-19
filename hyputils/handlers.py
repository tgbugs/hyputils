"""
    Implementation of various filter/handler pairs.
"""

import os


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


class dbSyncHandler(filterHandler):
    def __init__(self, *helpers):
        self.helpers = helpers

    def handler(self, message):
        for helper in self.helpers:
            helper(message)


class annotationSyncHandler(filterHandler):
    class DeletedAnno:
        deleted = True
        def __init__(self, id):
            self.id = id

    def __init__(self, annos, memoizer=None):
        from .hypothesis import HypothesisAnnotation as ha
        self.HypothesisAnnotation = ha
        self.annos = annos
        if memoizer is not None:
            self.memoizer = memoizer
        if not hasattr(self, 'memoizer'):
            print(f'WARNING: no memoizer has been supplied for {self.__class__.__name__}')

    def handler(self, message):
        anno = None
        try:
            act = message['options']['action']
            if act != 'create': # update delete
                mid = message['payload'][0]['id']
                for gone in [_ for _ in self.annos if _.id == mid]:
                    # FIXME slow, replace when we switch over to using dicts
                    self.annos.remove(gone)
                anno = self.DeletedAnno(mid)
            if act != 'delete':  # create update
                anno = self.HypothesisAnnotation(message['payload'][0])
                self.annos.append(anno)
            #print(len(self.annos), 'annotations.')
            if hasattr(self, 'memoizer'):
                self.memoizer.memoize_annos(self.annos)

            return anno  # we can't not return None
        except KeyError as e:
            embed()


class helperSyncHandler(annotationSyncHandler):
    def __init__(self, annos, *helpers, memoizer=None):
        super().__init__(annos, memoizer=memoizer)
        if helpers:
            self.helpers = helpers

    def handler(self, message):
        anno = super().handler(message)
        out = []  # can't use yield here

        if anno is None:
            raise TypeError(f'anno should not be None! Bad message:\n{message}')

        for helper in self.helpers:
            out.append(helper(anno, self.annos))

        return tuple(_ for _ in out if _ is not None)


class websocketServerHandler(filterHandler):
    def __init__(self, send_to_server):
        self.send = send_to_server

    def handler(self, message):
        self.send(message)


class slackHandler(filterHandler):
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
        import yaml
        from zdesk import Zendesk
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
        #print(message['payload'][0]['links']['incontext'])  # structure changed?
        print(message)


def getFilterHandlers():
    return [zendeskHandler(), printHandler()]  # order matters

