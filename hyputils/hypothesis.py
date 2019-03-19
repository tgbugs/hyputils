#!/usr/bin/env python3
from __future__ import print_function
import os
from os import environ, chmod
import json
import hashlib
import logging
import requests
from types import GeneratorType
from collections import Counter, defaultdict

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
UID = os.getuid()


class JEncode(json.JSONEncoder):
     def default(self, obj):
         if isinstance(obj, tuple):
             return list(obj)
         elif isinstance(obj, HypothesisAnnotation):
             return obj._row

         # Let the base class default method raise the TypeError
         return json.JSONEncoder.default(self, obj)


def group_to_memfile(group, post=lambda group_hash:None):
    m = hashlib.sha256()
    m.update(group.encode())
    group_hash = m.hexdigest()
    memfile = f'/tmp/annos-{UID}-{group_hash}.json'
    post(group_hash)
    return memfile


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

if 'CI' not in environ:
    hyp_logger.debug(' '.join((api_token, username, group)))  # sanity check

# simple uri normalization

def norm(iri):
    if '://' in iri:
        _scheme, iri_norm = iri.split('://', 1)
        if '?hypothesisAnnotationId=' in iri:
            iri_norm, junk = iri.split('?hypothesisAnnotationId=', 1)
    else:
        iri_norm = iri  # the creeping madness has co

    return iri_norm

# annotation retrieval and memoization

class NotOkError(Exception):
    def __init__(self, message, request):
        self.status_code = request.status_code
        self.reason = request.reason
        super().__init__(message)


class AnnoFetcher:
    lsu_default = '1900-01-01T00:00:00.000000+00:00'  # don't need, None is ok
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
        # FIXME batch the memoization of these?
        return [HypothesisAnnotation(r) for r in
                self.yield_from_api(search_after=search_after,
                                    limit=limit,
                                    max_results=max_results,
                                    stop_at=stop_at)]


class Memoizer(AnnoFetcher):  # TODO just use a database ...

    class GroupMismatchError(Exception):
        pass

    def __init__(self, memoization_file=None, api_token=api_token, username=username, group=group):
        super().__init__(api_token=api_token, username=username, group=group)
        if memoization_file is None:
            if group == '__world__':
                memoization_file = f'/tmp/annos-{UID}-__world__-{username}.json'
            else:
                memoization_file = group_to_memfile(group)
        self.memoization_file = memoization_file

    def check_group(self, annos):
        if annos:
            group = annos[0].group
            if self.group != group:
                raise self.GroupMismatchError(f'Groups do not match! {self.group} {group}')

    def get_annos_from_file(self):
        jblobs = []
        last_sync_updated = None
        if self.memoization_file is not None:
            try:
                with open(self.memoization_file, 'rt') as f:
                    jblobs_lsu = json.load(f)
                    jblobs, last_sync_updated = jblobs_lsu
                    if isinstance(last_sync_updated, HypothesisAnnotation):
                        jblobs = jblobs_lsu
                        last_sync_updated = last_sync_updated['updated']
                if jblobs is None:
                    raise ValueError('wat')
            except json.decoder.JSONDecodeError:
                with open(self.memoization_file, 'rt') as f:
                    data = f.read()
                if not data:
                    print('memoization file exists but is empty')
            except FileNotFoundError:
                print('memoization file does not exist')

        annos = [HypothesisAnnotation(jb) for jb in jblobs]
        self.check_group(annos)
        return annos, last_sync_updated

    def add_missing_annos(self, annos, last_sync_updated):
        self.check_group(annos)
        search_after = last_sync_updated
        # start from last_sync_updated because we assume that the websocket is unreliable
        new_annos = self.get_annos_from_api(search_after)  # FIXME batch these
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

    def update_annos_from_api(self, annos, helpers=tuple()):
        """ Assumes these are ordered by updated """
        # FIXME why aren't we just getting the group from the annos??
        self.check_group(annos)
        last_sync_updated = annos[-1].updated
        search_after = last_sync_updated
        # start from last_sync_updated because we assume that the websocket is unreliable
        new_annos = self.get_annos_from_api(search_after)
        if new_annos:
            new_ids = set(a.id for a in new_annos)
            for anno in tuple(annos):  # FIXME memory and perf issues?
                if anno.id in new_ids:
                    annos.remove(anno)

            annos.extend(new_annos)
            # TODO deal with updates
            self.memoize_annos(annos)
            for anno in new_annos:
                for Helper in helpers:
                    Helper(anno, annos)

    def memoize_annos(self, annos):
        # FIXME if there are multiple ws listeners we will have race conditions?
        if self.memoization_file is not None:
            print(f'annos updated, memoizing new version with, {len(annos)} members')
            do_chmod = False
            if not os.path.exists(self.memoization_file):
                do_chmod = True

            with open(self.memoization_file, 'wt') as f:
                lsu = annos[-1].updated if annos else None
                alsu = annos, lsu
                json.dump(alsu, f, cls=JEncode)

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
        if isinstance(row, HypothesisAnnotation):
            row = row._row

        self._row = row

    def _normalized(self):
        out = {}
        for k in dir(self):
            if not k.startswith('_'):
                v = getattr(self.__class__, k, None)  # need to walk up the mro
                if isinstance(v, property):
                    value = getattr(self, k)
                    if isinstance(value, GeneratorType):
                        value = list(value)

                    out[k] = value

        return out

    @property
    def id(self):
        return self._row['id']

    @property
    def user(self):
        return self._row['user'].replace('acct:','').replace('@hypothes.is','')

    @property
    def created(self):
        return self._row['created']

    @property
    def updated(self):
        return self._row['updated']

    @property
    def document(self):
        if 'document' in self._row:
            return self._row['document']
        else:
            return {}

    @property
    def filename(self):
        document = self.document
        if 'filename' in document:
            return document['filename']

    @property
    def doc_title(self):
        document = self.document
        if 'title' in document:
            title = document['title']
            if isinstance(title, list) and len(title):
                title = title[0]
        else:
            title = self.uri

        title = title.replace('"',"'")
        if not title:
            title = 'untitled'

        return title

    @property
    def links(self):
        document = self.document
        if 'link' in document:
            yield from document['link']

    @property
    def uri(self):
        if 'uri' in self._row:    # should it ever not?
            uri = self._row['uri']
        else:
             uri = "no uri field for %s" % self.id

        uri = uri.replace('https://via.hypothes.is/h/','').replace('https://via.hypothes.is/','')

        if uri.startswith('urn:x-pdf'):
            document = self.document
            for link in self.links:
                uri = link['href']
                if uri.encode('utf-8').startswith(b'urn:') == False:
                    break
            if uri.encode('utf-8').startswith(b'urn:') and 'filename' in document:
                uri = document['filename']

        return uri

    @property
    def tags(self):
        tags = []
        if 'tags' in self._row and self._row['tags'] is not None:
            tags = self._row['tags']
            if isinstance(tags, list):  # I find it hard to believe this is ever not true
                tags = [t.strip() for t in tags]
            else:
                raise BaseException('should never happen ...')

        return tags

    @property
    def text(self):
        text = ''
        if 'text' in self._row:
            text = self._row['text']

        return text

    @property
    def references(self):
        references = []
        if 'references' in self._row:
            references = self._row['references']

        return references

    @property
    def is_page_note(self):
        return self.type == 'pagenote'

    @property
    def type(self):
        if self.references:
            return 'reply'
        elif self.targets and any('selector' in t for t in self.targets):
            return 'annotation'
        else:
            return 'pagenote'

    @property
    def targets(self):
        # the spec says you can have multiple targets
        # the implementation only supports one at this time
        targets = []
        if 'target' in self._row:
            targets = self._row['target']

        return targets

    @property
    def selectors(self):
        for target in self.targets:
            if 'selector' in target:  # there are some that only have 'source'
                for selector in target['selector']:
                    yield selector

    def _selector_value(self, type, name):
        # obviously inefficient
        for selector in self.selectors:
            if 'type' in selector and selector['type'] == type:
                return selector[name]

    @property
    def prefix(self):
        return self._selector_value('TextQuoteSelector', 'prefix')

    @property
    def exact(self):
        return self._selector_value('TextQuoteSelector', 'exact')

    @property
    def suffix(self):
        return self._selector_value('TextQuoteSelector', 'suffix')

    @property
    def start(self):
        return self._selector_value('TextPositionSelector', 'start')

    @property
    def end(self):
        return self._selector_value('TextPositionSelector', 'end')

    @property
    def fragment_selector(self):
        return self._selector_value('FragmentSelector', 'value')

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
        yield from self.objects.values()  # don't sort unless required

    @property
    def uri_tags(self):
        """ a dictionary all (processed) tags for a given uri """
        if not hasattr(self, '_uri_tags'):
            uri_tags = defaultdict(set)
            for obj in self.objects.values():  # do not use self here because the
                # sorting in __iter__ above can be extremely slow
                uri_tags[obj.uri].update(obj._tags)

            self._uri_tags = dict(uri_tags)  # FIXME this will go stale

        return self._uri_tags

    @property
    def uris(self):
        """ uris that have been annotated with tags from this workflow """
        if hasattr(self, 'namespace'):
            return set(uri for uri, tags in self.uri_tags.items()
                       if any(tag.startswith(self.prefix_ast)
                              for tag in tags))
        else:
            return set(self.uri_tags)

    @property
    def orphans(self):
        for id in self._orphanedReplies:
            yield self.byId(id)

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
    _orphanedReplies = set()

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
        if cls._done_loading:  # TODO maybe better than done loading is 'consistent'?
            if not cls._tagIndex:
                printD('populating tags')
                # FIXME extremely inefficient on update
                # and we want this to update as replies appear
                # not all at once...
                # FIXME this does not update if new annos are added on the fly!
                [obj.populateTags() for obj in cls.objects.values()]

            return sorted(set.intersection(*(cls._tagIndex[tag] for tag in tags)))
        else:
            hyp_logger.warning('attempted to search by tags before done loading')

    def populateTags(self):
        # FIXME need a way to evict old annos on update
        for tag in self.tags:
            if tag not in self._tagIndex:
                self._tagIndex[tag] = {self}
            else:
                self._tagIndex[tag].add(self)

            tset = self._tagIndex[tag]
            if tset not in self._remove_self_from:
                self._remove_self_from.append((tag, tset))

    def depopulateTags(self):
        """ remove object from the tag index on delete """
        hyp_logger.debug(f'Removing {self._repr} from {len(self._remove_self_from)} tag sets')
        for tag, tset in self._remove_self_from:
            tset.remove(self)  # this should never error if everything is working correctly
            if not tset:  # remove unused tags from the index in depopulate
                self._tagIndex.pop(tag)

    @classmethod
    def byIri(cls, iri, prefix=False):
        norm_iri = norm(iri)
        for obj in cls.objects.values():
            norm_ouri = norm(obj.uri)
            if norm_ouri == norm_iri:
                yield obj
            elif prefix and norm_ouri.startswith(norm_iri):
                yield obj

    def __new__(cls, anno, annos):
        if not hasattr(cls, '_annos_list'):
            cls._annos_list = annos
        elif cls._annos_list is not annos:  # FIXME STOP implement a real annos (SyncList) class FFS
            for a in annos:
                if a not in cls._annos_list:
                    cls._annos_list.append(a)
            annos = cls._annos_list

        if hasattr(anno, 'deleted'):
            matches = [a for a in annos if a.id == anno.id]  # FIXME ick get rid of the list!
            for m in matches:
                cls._annos_list.remove(m)

            if anno.id in cls._annos:  # it is set to True by convetion
                cls._annos.pop(anno.id)  # insurance
            #else:
                #print("It's ok we already deleted", anno.id)
            if anno.id in cls.objects:
                obj = cls.objects.pop(anno.id)  # this is what we were missing
                obj.depopulateTags()
                #print('Found the sneek.', anno.id)
            return  # our job here is done

        if not cls._annos or len(cls._annos) < len(annos):  # much faster (as in O(n**2) -> O(1)) to populate once at the start
            # we should not need `if not a.deleted` because a should not be in annos
            cls._annos.update({a.id:a for a in annos})  # FIXME this fails on deletes...
            if len(cls._annos) != len(annos):
                print(f'WARNING it seems you have duplicate entries for annos: {len(cls._annos)} != {len(annos)}')
        try:
            self = cls.objects[anno.id]
            if self._updated == anno.updated:
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
        self._remove_self_from = []

        if self._tagIndex:
            # if tagIndex is not empty and we make it to __init__
            # then this anno helper has not been put into the tag index
            # FIXME stale annos in the tag index are likely an issue
            self.populateTags()

        if hasattr(self, '_uri_tags'):  # keep uri_tags in sync
            if anno.uri not in self._uri_tags:
                self._uri_tags[self.uri] = set()

            self._uri_tags[self.uri].update(self._tags)  # use _tags since tags can make many calls

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
    def _anno(self):
        try:
            return self._annos[self.id]  # this way updateds to annos will propagate
        except KeyError as e:
            #from IPython import embed
            #embed()
            print(self._tagIndex)
            raise e

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
    @property
    def uri(self): return self._anno.uri

    @classmethod
    def getAnnoById(cls, id_):
        try:
            return cls._annos[id_]
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
                        #print('Orphaned reply', self.shareLink, f"{self.classn}.byId('{self.id}')")
                        self._orphanedReplies.add(self.id)
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

