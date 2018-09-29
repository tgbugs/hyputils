#!/usr/bin/env python3
from __future__ import print_function
import os
from os import environ, chmod
import json
import pickle
import logging
import requests
from collections import Counter

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from misc.debug import TDB
    tdb=TDB()
    printD=tdb.printD
except ImportError:
    printD = print

# read environment variables # FIXME not the most modular...

api_token = environ.get('HYP_API_TOKEN', 'TOKEN')  # Hypothesis API token
username = environ.get('HYP_USERNAME', 'USERNAME') # Hypothesis username
group = environ.get('HYP_GROUP', '__world__')

if 'CI' not in environ:
    print(api_token, username, group)  # sanity check


def makeSimpleLogger(name):
    # TODO use extra ...
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()  # FileHander goes to disk
    formatter = logging.Formatter('[%(asctime)s] - %(levelname)s - %(name)s - %(message)s')  # TODO file and lineno ...
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


hyp_logger = makeSimpleLogger('hyputils.hypothesis')

# annotation retrieval and memoization

class NotOkError(Exception):
    def __init__(self, message, request):
        self.status_code = request.status_code
        self.reason = request.reason
        super().__init__(message)


class AnnoFetcher:
    def __init__(self, api_token=api_token, username=username, group=group):
        if api_token == 'TOKEN':
            print('\x1b[31mWARNING:\x1b[0m NO API TOKEN HAS BEEN SET!')
        self.api_token = api_token
        self.username = username
        self.group = group

    def __call__(self):
        return self.get_annos()

    def h(self):
        return HypothesisUtils(username=self.username, token=self.api_token, group=self.group)

    def yield_from_api(self, search_after=None, limit=None, max_results=None, stop_at=None):
        # use stop before if you want to be evil and hit the api in parallel
        print('fetching after', search_after)
        # hard code these to simplify assumptions
        order = 'asc'
        sort = 'updated'
        h = self.h()
        params = {'order':order,
                  'sort':sort,
                  'group':h.group}
        if search_after:
            params['search_after'] = search_after
        if max_results is None and self.group == '__world__':
            hyp_logger.info(f'searching __world__ as {self.username} since max_results was not set')
            params['user'] = self.username
        if limit is not None:
            params['limit'] = limit

        for row in h.search_all(params, max_results=max_results, stop_at=stop_at):
            yield row

    def get_annos_from_api(self, search_after=None, limit=None, max_results=None, stop_at=None):
        return [HypothesisAnnotation(r) for r in
                self.yield_from_api(search_after=search_after,
                                    limit=limit,
                                    max_results=max_results,
                                    stop_at=stop_at)]


class Memoizer(AnnoFetcher):  # TODO just use a database ...

    class GroupMismatchError(Exception):
        pass

    def __init__(self, memoization_file, api_token=api_token, username=username, group=group):
        super().__init__(api_token=api_token, username=username, group=group)
        self.memoization_file = memoization_file

    def check_group(self, annos):
        if annos:
            group = annos[0].group
            if self.group != group:
                raise self.GroupMismatchError(f'Groups do not match! {self.group} {group}')

    def get_annos_from_file(self):
        annos = []
        last_sync_updated = None
        if self.memoization_file is not None:
            try:
                with open(self.memoization_file, 'rb') as f:
                    annos_lsu = pickle.load(f)
                    annos, last_sync_updated = annos_lsu
                    if isinstance(last_sync_updated, HypothesisAnnotation):
                        annos = annos_lsu
                        last_sync_updated = last_sync_updated['updated']
                if annos is None:
                    raise ValueError('wat')
            except FileNotFoundError:
                print('memoization file does not exist')

        self.check_group(annos)
        return annos, last_sync_updated

    def add_missing_annos(self, annos, last_sync_updated):
        self.check_group(annos)
        search_after = last_sync_updated
        # start from last_sync_updated because we assume that the websocket is unreliable
        new_annos = self.get_annos_from_api(search_after)
        if not new_annos:
            return annos
        merged = annos + new_annos
        merged_unique = sorted(set(merged), key=lambda a: a.updated)
        dupes = [sorted([a for a in merged_unique if a.id == id], key=lambda a: a.updated)
                for id, count in Counter(anno.id for anno in merged_unique).most_common()
                if count > 1]

        will_stay = [dupe[-1] for dupe in dupes]
        to_remove = [a for dupe in dupes for a in dupe[:-1]]

        la = len(annos)
        ld = len(dupes)
        lm = len(merged)
        lmu = len(merged_unique)
        [merged_unique.remove(d) for d in to_remove]  # FIXME in the db context these need to be updates
        lmuc = len(merged_unique)

        print('added', lmuc - la, 'new annotations')
        print('updated', ld, 'annotations')

        if la != lmuc or dupes:
            self.memoize_annos(merged_unique)

        return merged_unique

    def memoize_annos(self, annos):
        # FIXME if there are multiple ws listeners we will have race conditions?
        if self.memoization_file is not None:
            print(f'annos updated, memoizing new version with, {len(annos)} members')
            do_chmod = False
            if not os.path.exists(self.memoization_file):
                do_chmod = True

            with open(self.memoization_file, 'wb') as f:
                alsu = annos, annos[-1].updated
                pickle.dump(alsu, f)

            if do_chmod:
                chmod(self.memoization_file, 0o600)

        else:
            print(f'No memoization file, not saving.')

    def get_annos(self):
        annos, last_sync_updated = self.get_annos_from_file()
        if not annos:
            new_annos = self.get_annos_from_api()
            self.memoize_annos(new_annos)
            return new_annos
        else:
            return self.add_missing_annos(annos, last_sync_updated)

    def add_anno(self, anno, annos):
        annos.append(anno)
        self.memoize_annos(annos)

    def del_anno(self, id_, annos, memoize=True):
        # FIXME this is is SUPER slow
        matches = [a for a in annos if a.id == id_]
        if not matches:
            raise ValueError(f'No annotation with id={id_} could be found.')
        else:
            for match in matches:
                annos.remove(match)
            if memoize:
                self.memoize_annos(annos)

    def update_anno(self, anno, annos):
        self.del_anno(anno.id, annos, memoize=False)
        self.add_anno(anno, annos)

    def update_annos_from_api_response(resp, annos):
        # XXX NOTE this will collide with websocket if unmanaged
        # therefore we will need to somehow sync with that to make sure
        # everything remains sane... maybe a shared log that the
        # websocket handler can peak at an confirm or something
        # (that is going to be a weird boundary to navigate)
        if resp.status_code == 200:
            if resp.request.method == 'GET':
                anno = HypothesisAnnotation(resp.json())
                self.update_anno(anno, annos)
                return anno
            elif resp.request.method == 'POST':
                anno = HypothesisAnnotation(resp.json())
                self.add_anno(anno, annos)
                return anno
            elif resp.request.method == 'PATCH':
                anno = HypothesisAnnotation(resp.json())
                self.update_anno(anno, annos)
                return anno
            elif resp.request.method == 'DELETE':
                id = resp.json()['id']
                self.del_anno(id, annos)

#
# url helpers

def idFromShareLink(link):  # XXX warning this will break
    if 'hyp.is' in link:
        id_ = link.split('/')[3]
        return id_

def shareLinkFromId(id_):
    return 'https://hyp.is/' + id_

# API classes

class HypothesisUtils:
    """ services for authenticating, searching, creating annotations """
    def __init__(self, username=None, token=None, group=None, domain=None, limit=None):
        if domain is None:
            self.domain = 'hypothes.is'
        else:
            self.domain = domain
        if username is not None:
            self.username = username
        if token is not None:
            self.token = token
        self.app_url = 'https://%s/app' % self.domain
        self.api_url = 'https://%s/api' % self.domain
        self.query_url_template = 'https://%s/api/search?{query}' % self.domain
        self.search_url_template = 'https://%s/search?q={query}' % self.domain
        self.group = group if group is not None else '__world__'
        self.single_page_limit = 200 if limit is None else limit  # per-page, the api honors limit= up to (currently) 200
        self.permissions = {
                "read": ['group:' + self.group],
                "update": ['acct:' + self.username + '@hypothes.is'],
                "delete": ['acct:' + self.username + '@hypothes.is'],
                "admin":  ['acct:' + self.username + '@hypothes.is']
                }
        self.ssl_retry = 0

    def authenticated_api_query(self, query_url=None):
        try:
            headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8'}
            r = requests.get(query_url, headers=headers)
            obj = r.json()
            if r.ok:
                return obj
            else:
                raise NotOkError(f'response was not ok! {r.reason} {obj}', r)

        except requests.exceptions.SSLError as e:
            if self.ssl_retry < 5:
                self.ssl_retry += 1
                print('Ssl error at level', self.ssl_retry, 'retrying....')
                return self.authenticated_api_query(query_url)
            else:
                self.ssl_retry = 0
                hyp_logger.error(e)
                return {'ERROR':True, 'rows':tuple()}
        except BaseException as e:
            hyp_logger.error(e)
            #print('Request, status code:', r.status_code)  # this causes more errors...
            return {'ERROR':True, 'rows':tuple()}

    def make_annotation_payload_with_target_using_only_text_quote(self, url, prefix, exact, suffix, text, tags):
        """Create JSON payload for API call."""
        if exact is None:
            target = [{'source':url}]
        else:
            target = [{
                "scope": [url],
                "selector":
                [{
                    "type": "TextQuoteSelector",
                    "prefix": prefix,
                    "exact": exact,
                    "suffix": suffix
                },]
            }]
        if text == None:
            text = ''
        if tags == None:
            tags = []
        payload = {
            "uri": url,
            "user": 'acct:' + self.username + '@hypothes.is',
            "permissions": self.permissions,
            "group": self.group,
            "target": target,
            "tags": tags,
            "text": text
        }
        return payload

    def create_annotation_with_target_using_only_text_quote(self, url=None, prefix=None,
               exact=None, suffix=None, text=None, tags=None, tag_prefix=None):
        """Call API with token and payload, create annotation (using only text quote)"""
        payload = self.make_annotation_payload_with_target_using_only_text_quote(url, prefix, exact, suffix, text, tags)
        try:
            r = self.post_annotation(payload)
        except BaseException as e:
            hyp_logger.error(e)
            r = None  # if we get here someone probably ran the bookmarklet from firefox or the like
        return r

    def head_annotation(self, id):
        # used as a 'kind' way to look for deleted annotations
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        r = requests.head(self.api_url + '/annotations/' + id, headers=headers)
        return r

    def get_annotation(self, id):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        r = requests.get(self.api_url + '/annotations/' + id, headers=headers)
        return r

    def post_annotation(self, payload):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.post(self.api_url + '/annotations', headers=headers, data=data.encode('utf-8'))
        return r

    def patch_annotation(self, id, payload):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.patch(self.api_url + '/annotations/' + id, headers=headers, data=data.encode('utf-8'))
        return r

    def delete_annotation(self, id):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        r = requests.delete(self.api_url + '/annotations/' + id, headers=headers)
        return r

    def search_all(self, params={}, max_results=None, stop_at=None):
        """Call search API with pagination, return rows """
        sort_by = params['sort'] if 'sort' in params else 'updated'
        if stop_at:
            if not isinstance(stop_at, str):
                raise TypeError('stop_at should be a string')

            dont_stop = (lambda r: r[sort_by] <= stop_at  # when ascending things less than stop are ok
                         if 'order' in params and params['order'] == 'asc'
                         else lambda r: r[sort_by] >= stop_at)

        if max_results:
            limit = 200 if 'limit' not in params else params['limit']  # FIXME hardcoded
            if max_results < limit:
                params['limit'] = max_results

        #sup_inf = max if params['order'] = 'asc' else min  # api defaults to desc
        # trust that rows[-1] works rather than potentially messsing stuff if max/min work differently
        nresults = 0
        while True:
            obj = self.search(params)
            rows = obj['rows']
            lr = len(rows)
            nresults += lr
            if lr is 0:
                return

            stop = None
            if max_results:
                if nresults >= max_results:
                    stop = max_results - nresults  + lr

            if stop_at:
                for row in rows[:stop]:
                    if dont_stop(row):
                        yield row
                    else:
                        return

            else:
                for row in rows[:stop]:
                    yield row

            if stop:
                return

            search_after = rows[-1][sort_by]
            params['search_after'] = search_after
            print('searching after', search_after)

    def search_url(self, **params):
        return self.search_url_template.format(query=urlencode(params, True).replace('=','%3A'))  # = > :

    def query_url(self, **params):
        return self.query_url_template.format(query=urlencode(params, True))

    def search(self, params={}):
        """ Call search API, return a dict """
        if 'offset' not in params:
            params['offset'] = 0
        if 'limit' not in params or 'limit' in params and params['limit'] is None:
            params['limit'] = self.single_page_limit
        obj = self.authenticated_api_query(self.query_url(**params))
        return obj


class HypothesisAnnotation:
    """Encapsulate one row of a Hypothesis API search."""
    def __init__(self, row):
        self._row = row
        self.type = None
        self.id = row['id']
        self.created = row['created']
        self.updated = row['updated']
        self.user = row['user'].replace('acct:','').replace('@hypothes.is','')

        if 'uri' in row:    # should it ever not?
            self.uri = row['uri']
        else:
             self.uri = "no uri field for %s" % self.id
        self.uri = self.uri.replace('https://via.hypothes.is/h/','').replace('https://via.hypothes.is/','')

        if self.uri.startswith('urn:x-pdf') and 'document' in row:
            if 'link' in row['document']:
                self.links = row['document']['link']
                for link in self.links:
                    self.uri = link['href']
                    if self.uri.encode('utf-8').startswith(b'urn:') == False:
                        break
            if self.uri.encode('utf-8').startswith(b'urn:') and 'filename' in row['document']:
                self.uri = row['document']['filename']

        if 'document' in row and 'title' in row['document']:
            t = row['document']['title']
            if isinstance(t, list) and len(t):
                self.doc_title = t[0]
            else:
                self.doc_title = t
        else:
            self.doc_title = self.uri
        if self.doc_title is None:
            self.doc_title = ''
        self.doc_title = self.doc_title.replace('"',"'")
        if self.doc_title == '': self.doc_title = 'untitled'

        self.tags = []
        if 'tags' in row and row['tags'] is not None:
            self.tags = row['tags']
            if isinstance(self.tags, list):
                self.tags = [t.strip() for t in self.tags]

        self.text = ''
        if 'text' in row:
            self.text = row['text']

        self.references = []
        if 'references' in row:
            self.type = 'reply'
            self.references = row['references']

        self.target = []
        if 'target' in row:
            self.target = row['target']

        self.is_page_note = False
        try:
            if self.references == [] and self.target is not None and len(self.target) and isinstance(self.target,list) and 'selector' not in self.target[0]:
                self.is_page_note = True
                self.type = 'pagenote'
        except BaseException as e:
            hyp_logger.error(e)

        if 'document' in row and 'link' in row['document']:
            self.links = row['document']['link']
            if not isinstance(self.links, list):
                self.links = [{'href':self.links}]
        else:
            self.links = []

        self.start = self.end = self.prefix = self.exact = self.suffix = None
        try:
            if isinstance(self.target,list) and len(self.target) and 'selector' in self.target[0]:
                self.type = 'annotation'
                selectors = self.target[0]['selector']
                for selector in selectors:
                    if 'type' in selector and selector['type'] == 'TextQuoteSelector':
                        try:
                            self.prefix = selector['prefix']
                            self.exact = selector['exact']
                            self.suffix = selector['suffix']
                        except BaseException as e:
                            hyp_logger.error(e)
                    if 'type' in selector and selector['type'] == 'TextPositionSelector' and 'start' in selector:
                        self.start = selector['start']
                        self.end = selector['end']
                    if 'type' in selector and selector['type'] == 'FragmentSelector' and 'value' in selector:
                        self.fragment_selector = selector['value']

        except BaseException as e:
            hyp_logger.error(e)

    @property
    def group(self): return self._row['group']

    @property
    def permissions(self): return {k:v for k,v in self._row['permissions'].items()}

    def __eq__(self, other):
        # text and tags can change, if exact changes then the id will also change
        return self.id == other.id and self.text == other.text and set(self.tags) == set(other.tags) and self.updated == other.updated

    def __hash__(self):
        return hash(self.id + self.text + self.updated)

    def __lt__(self, other):
        return self.updated < other.updated

    def __gt__(self, other):
        return not self.__lt__(other)


class iterclass(type):
    def __iter__(self):
        yield from sorted(self.objects.values())


# HypothesisHelper class customized to deal with replacing
#  exact, text, and tags based on its replies
#  also for augmenting the annotation with distinct fields
#  using annotation-text:exact or something like that... (currently using PROTCUR:annotation-exact which is super akward)
#  eg annotation-text:children to say exactly what the fields are when there needs to be more than one
#  it is possible to figure most of them out from their content but not always
class HypothesisHelper(metaclass=iterclass):  # a better HypothesisAnnotation
    """ A wrapper around sets of hypothes.is annotations
        with referential structure an pretty printing. """
    objects = {}  # TODO updates # NOTE: all child classes need their own copy of objects
    _tagIndex = {}
    _replies = {}
    reprReplies = True
    _embedded = False
    _done_loading = False
    _annos = {}

    @classmethod
    def addAnno(cls, anno):
        return cls(anno, [anno])

    @classmethod
    def byId(cls, id_):
        try:
            return next(v for v in cls.objects.values()).getObjectById(id_)
        except StopIteration as e:
            raise Warning(f'{cls.__name__}.objects has not been populated with annotations yet!') from e

    @classmethod
    def byTags(cls, *tags):
        if not cls._tagIndex:
            printD('populating tags')
            # FIXME extremely inefficient on update
            # and we want this to update as replies appear
            # not all at once...
            # FIXME this does not update if new annos are added on the fly!
            for obj in cls.objects.values():
                for tag in obj.tags:
                    if tag not in cls._tagIndex:
                        cls._tagIndex[tag] = {obj}
                    else:
                        cls._tagIndex[tag].add(obj)

        return sorted(set.intersection(*(cls._tagIndex[tag] for tag in tags)))

    def __new__(cls, anno, annos):
        if not hasattr(cls, '_annos_list'):
            cls._annos_list = annos
        elif cls._annos_list is not annos:  # FIXME STOP implement a real annos (SyncList) class FFS
            for a in annos:
                if a not in cls._annos_list:
                    cls._annos_list.append(a)
            annos = cls._annos_list

        if hasattr(anno, 'deleted'):
            if anno.id in cls._annos:  # it is set to True by convetion
                cls._annos.pop(anno.id)  # insurance
            #else:
                #print("It's ok we already deleted", anno.id)
            if anno.id in cls.objects:
                cls.objects.pop(anno.id)  # this is what we were missing
                #print('Found the sneek.', anno.id)
            return  # our job here is done

        if not cls._annos or len(cls._annos) < len(annos):  # much faster (as in O(n**2) -> O(1)) to populate once at the start
            # we should not need `if not a.deleted` because a should not be in annos
            cls._annos.update({a.id:a for a in annos})  # FIXME this fails on deletes...
            if len(cls._annos) != len(annos):
                print(f'WARNING it seems you have duplicate entries for annos: {len(cls._annos)} != {len(annos)}')
        try:
            self = cls.objects[anno.id]
            if self._text == anno.text and self._tags == anno.tags:
                #printD(f'{self.id} already exists')
                return self
            else:
                #printD(f'{self.id} already exists but something has changed')
                cls._annos[anno.id] = anno  # update to the new anno version
                self.__init__(anno, annos)  # just updated the underlying refs no worries
                return self
        except KeyError:
            #printD(f'{anno.id} doesnt exist')
            return super().__new__(cls)

    def __init__(self, anno, annos):
        self._recursion_blocker = False
        self.annos = annos
        self.id = anno.id  # hardset this to prevent shenanigans
        self.objects[self.id] = self

        #if self.objects[self.id] is None:
            #printD('WAT', self.id)
        self.hasAstParent = False
        self.parent  # populate self._replies before the recursive call
        if len(self.objects) == len(annos):
            self.__class__._done_loading = True

    @property
    def classn(self):
        return self.__class__.__name__

    @property
    def _repr(self):
        return self.classn + f".byId('{self.id}')"

    @property
    def _anno(self): return self._annos[self.id]  # this way updateds to annos will propagate

    # protect the original annotation from modification
    @property
    def _permissions(self): return self._anno.permissions
    @property
    def _type(self): return self._anno.type
    @property
    def _exact(self): return self._anno.exact
    @property
    def _text(self): return self._anno.text
    @property
    def _tags(self): return self._anno.tags
    @property
    def _updated(self): return self._anno.updated  # amusing things happen if you use self._anno.tags instead...
    @property
    def references(self): return self._anno.references

    # we don't have any rules for how to modify these yet
    @property
    def exact(self): return self._exact
    @property
    def text(self): return self._text
    @property
    def tags(self): return self._tags
    @property
    def updated(self): return self._updated

    def getAnnoById(self, id_):
        try:
            return self._annos[id_]
        except KeyError as e:
            #print('could not find', id_, shareLinkFromId(id_))
            return None

    def getObjectById(self, id_):
        try:
            return self.objects[id_]
        except KeyError as e:
            anno = self.getAnnoById(id_)
            if anno is None:
                #self.objects[id_] = None  # don't do this it breaks the type on objects
                #print('Problem in', self.shareLink)  # must come after self.objects[id_] = None else RecursionError
                if not self._recursion_blocker:
                    if self._type == 'reply':
                        print('Orphaned reply', self.shareLink, f"{self.classn}.byId('{self.id}')")
                    else:
                        print('Problem in', self.shareLink, f"{self.classn}.byId('{self.id}')")
                return None
            else:
                h = self.__class__(anno, self.annos)
                return h

    @property
    def shareLink(self):  # FIXME just look it up?!
        self._recursion_blocker = True
        if self.parent is not None:
            link = self.parent.shareLink
            # call link before unset recursion to prevent cases
            # where an intermediate parent was deleted
            self._recursion_blocker = False
            return link
        else:
            self._recursion_blocker = False
            return shareLinkFromId(self.id)

    @property
    def htmlLink(self):
        return self._anno._row['links']['html']

    @property
    def parent(self):
        if not self.references:
            return None
        else:
            for parent_id in self.references[::-1]:  # go backward to get the direct parent first, slower for shareLink but ok
                parent = self.getObjectById(parent_id)
                if parent is not None:
                    if parent.id not in self._replies:
                        self._replies[parent.id] = set()
                    self._replies[parent.id].add(self)
                    return parent
                else:
                    #printD(f"Parent gone for {self.__class__.__name__}.byId('{self.id}'}")
                    pass

    @property
    def replies(self):
        # for the record, the naieve implementation of this
        # looping over annos everytime is 3 orders of magnitude slower
        if self._done_loading:
            if self.id not in self._replies:
                self._replies[self.id] = set()
            return self._replies[self.id]  # we use self.id here instead of self to avoid recursion on __eq__
        else:
            print('WARNING: Not done loading annos, you will be missing references!')
            return set()


    def __eq__(self, other):
        return (type(self) == type(other) and
                self.id == other.id and
                self.text == other.text and
                set(self.tags) == set(other.tags) and
                self.updated == other.updated)

    def __hash__(self):
        return hash(self.__class__.__name__ + self.id)

    def __lt__(self, other):
        return self.updated < other.updated

    def __gt__(self, other):
        return not self.__lt__(other)

    @property
    def _python__repr__(self):
        return f"{self.__class__.__name__}.byId('{self.id}')"

    def __repr__(self, depth=0, format__repr__for_children='', html=False, number='*'):
        start = '|' if depth else ''
        SPACE = '&nbsp;' if html else ' '
        t = SPACE * 4 * depth + start

        parent_id =  f"\n{t}parent_id:    {self.parent.id} {self.parent._python__repr__}" if self.parent else ''
        exact_text = f'\n{t}exact:        {self.exact}' if self.exact else ''

        text_align = 'text:         '
        lp = f'\n{t}'
        text_line = lp + ' ' * len(text_align)
        text_text = lp + text_align + self.text.replace('\n', text_line) if self.text else ''
        tag_text =   f'\n{t}tags:         {self.tags}' if self.tags else ''

        replies = ''.join(r.__repr__(depth + 1) for r in self.replies)
        rep_ids = f'\n{t}replies:      ' + ' '.join(r._python__repr__ for r in self.replies)
        replies_text = (f'\n{t}replies:{replies}' if self.reprReplies else rep_ids) if replies else ''
        link = self.shareLink
        if html: link = atag(link, link)
        startn = '\n' if not isinstance(number, int) or number > 1 else ''
        return (f'{startn}{t.replace("|","")}{number:-<20}'
                f"\n{t}{self.__class__.__name__ + ':':<14}{link} {self._python__repr__}"
                f'\n{t}user:         {self._anno.user}'
                f'{parent_id}'
                f'{exact_text}'
                f'{text_text}'
                f'{tag_text}'
                f'{replies_text}'
                f'{format__repr__for_children}'
                f'\n{t}{"":_<20}')

