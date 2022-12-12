#!/usr/bin/env python3
from __future__ import print_function
from os import environ, chmod
import json
import shutil
import hashlib
import pathlib
import logging
from time import sleep
from types import GeneratorType
from collections import defaultdict
import psutil  # sigh
import appdirs
import requests

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

# read environment variables # FIXME not the most modular...

__all__ = ['api_token', 'username', 'group', 'group_to_memfile',
           'idFromShareLink', 'shareLinkFromId',
           'AnnoFetcher', 'Memoizer',
           'HypothesisUtils', 'HypothesisHelper', 'Annotation', 'HypAnnoId']

api_token = environ.get('HYP_API_TOKEN', 'TOKEN')   # Hypothesis API token
username = environ.get('HYP_USERNAME', 'USERNAME')  # Hypothesis username
group = environ.get('HYP_GROUP', '__world__')
ucd = appdirs.user_cache_dir()


class JEncode(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, tuple):
            return list(obj)
        elif isinstance(obj, HypothesisAnnotation):
            return obj._row

        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def group_to_memfile(group, post=lambda group_hash: None):
    if group != '__world__':
        m = hashlib.sha256()
        m.update(group.encode())
        group_hash = m.hexdigest()
    else:
        group_hash = group

    memfile = pathlib.Path(ucd, 'hyputils', f'annos-{group_hash}.json')
    post(group_hash)
    memfile.parent.mkdir(exist_ok=True, parents=True)  # FIXME remove after orthauth switch
    return memfile


def makeSimpleLogger(name, level=logging.INFO):
    # TODO use extra ...
    logger = logging.getLogger(name)
    if logger.handlers:  # prevent multiple handlers
        return logger

    logger.setLevel(level)
    ch = logging.StreamHandler()  # FileHander goes to disk
    fmt = ('[%(asctime)s] - %(levelname)8s - '
           '%(name)14s - '
           '%(filename)16s:%(lineno)-4d - '
           '%(message)s')
    formatter = logging.Formatter(fmt)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


log = makeSimpleLogger('hyputils')
logd = log.getChild('data')

if 'CI' not in environ:
    log.debug(' '.join((api_token, username, group)))  # sanity check

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

    def __init__(self, api_token=api_token, username=username, group=group,
                 **kwargs):
        if api_token == 'TOKEN':
            log.warning('\x1b[31mWARNING:\x1b[0m NO API TOKEN HAS BEEN SET!')
        self.api_token = api_token
        self.username = username
        self.group = group

    def __call__(self):
        return self.get_annos()

    def h(self):
        return HypothesisUtils(username=self.username,
                               token=self.api_token,
                               group=self.group)

    def yield_from_api(self,
                       search_after=None,
                       limit=None,
                       max_results=None,
                       stop_at=None):
        # use stop at if you want to be evil and hit the api in parallel
        log.info(f'fetching after {search_after}')
        # hard code these to simplify assumptions
        order = 'asc'
        sort = 'updated'
        h = self.h()
        params = {'order': order,
                  'sort': sort,
                  'group': h.group}
        if search_after:
            params['search_after'] = search_after
        if max_results is None and self.group == '__world__':
            log.info(f'searching __world__ as {self.username} '
                     'since max_results was not set')
            params['user'] = self.username
        if limit is not None:
            params['limit'] = limit

        for row in h.search_all(
                params, max_results=max_results, stop_at=stop_at):
            yield row

    def get_annos_from_api(self,
                           search_after=None,
                           limit=None,
                           max_results=None,
                           stop_at=None):
        return [HypothesisAnnotation(r) for r in
                self.yield_from_api(search_after=search_after,
                                    limit=limit,
                                    max_results=max_results,
                                    stop_at=stop_at)]


class AnnoReader:

    class GroupMismatchError(Exception):
        pass

    def __init__(self, memoization_file, group, *args, **kwargs):
        self.group = group
        if memoization_file is None:
            memoization_file = group_to_memfile(group)
        elif not isinstance(memoization_file, pathlib.Path):
            memoization_file = pathlib.Path(memoization_file)

        self.memoization_file = memoization_file

    def __call__(self):
        return self.get_annos()

    def get_annos(self):
        annos, last_sync_updated = self.get_annos_from_file()
        return annos

    def get_annos_from_file(self, file=None):
        if file is None:
            file = self.memoization_file

        jblobs = []
        last_sync_updated = None
        if file is not None:
            try:
                with open(file, 'rt') as f:
                    jblobs_lsu = json.load(f)

                try:
                    jblobs, last_sync_updated = jblobs_lsu
                    if not isinstance(last_sync_updated, str):
                        msg = ('We have probably hit the rare case where there'
                               ' are exactly two annotations in a cache file.')
                        raise ValueError(msg)
                except ValueError:
                    jblobs = jblobs_lsu
                    last_sync_updated = jblobs[-1]['updated']

                if jblobs is None:
                    raise ValueError('wat')
            except json.decoder.JSONDecodeError:
                with open(file, 'rt') as f:
                    data = f.read()
                if not data:
                    log.info('memoization file exists but is empty')
            except FileNotFoundError:
                log.info('memoization file does not exist')

        annos = [HypothesisAnnotation(jb) for jb in jblobs]
        self.check_group(annos)
        return annos, last_sync_updated

    def check_group(self, annos):
        if annos:
            group = annos[0].group
            if self.group != group:
                msg = f'Groups do not match! {self.group} {group}'
                raise self.GroupMismatchError(msg)


class Memoizer(AnnoReader, AnnoFetcher):  # TODO just use a database ...

    def __init__(self, memoization_file=None,
                 api_token=api_token,
                 username=username,
                 group=group):
        # SIGH
        AnnoReader.__init__(self,
            memoization_file=memoization_file,
            group=group)

        AnnoFetcher.__init__(self,
            memoization_file=memoization_file,
            api_token=api_token,
            username=username,
            group=group)

        lock_name = '.lock-' + self.memoization_file.stem
        self._lock_folder = self.memoization_file.parent / lock_name

    def add_missing_annos(self, annos, last_sync_updated):  # XXX deprecated
        """ this modifies annos in place """
        self.check_group(annos)
        search_after = last_sync_updated
        # start from last_sync_updated since the websocket is unreliable
        new_annos = self._stream_annos_from_api(annos, search_after)
        return annos

    def update_annos_from_api(self,
                              annos,
                              helpers=tuple(),
                              start_after=None,
                              stop_at=None,
                              batch_size=2000):
        self.check_group(annos)
        if annos:
            if start_after is not None:
                raise TypeError('cannot have both non-empty annos and '
                                'not None start_after at the same time')
            last_sync_updated = annos[-1].updated
            search_after = last_sync_updated

        new_annos = self._stream_annos_from_api(annos,
                                                search_after,
                                                stop_at,
                                                batch_size,
                                                helpers)

        for anno in new_annos:
            for Helper in helpers:
                Helper(anno, annos)

        return new_annos

    def _stream_annos_from_api(self,
                               annos,
                               search_after,
                               stop_at=None,
                               batch_size=2000,
                               helpers=tuple()):
        # BUT FIRST check to make sure that no one else is in the middle of fetching into our anno file
        # YES THIS USES A LOCK FILE, SIGH
        can_update = not self._lock_folder.exists()
        if can_update:
            # TODO in a multiprocess context streaming anno updates
            # is a nightmare, even in this context if we call get_annos
            # more than once there is a risk that only some processes
            # will get the new annos, though I guess that is ok
            # in the sense that they will go look for new annos starting
            # wherever they happen to be and will double pull any annos
            # that were previously pulled by another process in addition
            # to any annoations that happend after the other process pulled
            # the only inconsistency would be if an annoation was deleted
            # since we already deal with the update case
            self._lock_folder.mkdir()
            new_annos = self._can_update(annos, search_after, stop_at, batch_size)
        elif self._locking_process_dead():
            if self._lock_pid_file.exists():
                # folder might exist by itself with no lock-pid file
                self._unlock_pid()

            _search_after = self._lock_folder_lsu()
            search_after = (search_after
                            if _search_after is None else
                            _search_after)

            new_annos = self._can_update(annos, search_after, stop_at, batch_size)
        else:
            new_annos = self._cannot_update(annos)

        return new_annos

    def _can_update(self, annos, search_after, stop_at, batch_size):
        """ only call this if we can update"""
        try:
            self._write_lock_pid()
            gen = self.yield_from_api(search_after=search_after,
                                      stop_at=stop_at)
            try:
                while True:
                    first = [next(gen)]  # stop iteration breaks the loop
                    rest = [anno for i, anno in zip(range(batch_size - 1), gen)]
                    batch = first + rest
                    lsu = batch[-1]['updated']
                    file = self._lock_folder / lsu  # FIXME windows
                    with open(file, 'wt') as f:
                        json.dump(batch, f)
            except StopIteration:
                pass

        except:
            raise
        else:  # I think this is the first time I've ever had to use this
            new_annos = self._lock_folder_to_json(annos)
            shutil.rmtree(self._lock_folder)
            return new_annos
        finally:
            if self._lock_pid_file.exists():
                self._unlock_pid()

    def _cannot_update(self, annos):
        # we have to block here until the annos are updated and the
        # lock folder is removed so we can extend the current annos
        while True:
            sleep(1)  # sigh
            # FIXME in theory this wait could
            # lead to some workers never waking up
            # if calls to update from other workers
            # happen frequently enough
            if not self._lock_folder.exists():
                break

        all_annos, lsu = self.get_annos_from_file()
        # this approach is safter than direct comparison of all_annos and annos
        # because it makes it possible to detect duplicates from updates
        new_annos = [a for a in all_annos if a.updated > lsu]
        self._merge_new_annos(annos, new_annos)
        # we don't need to memoize here
        return new_annos


    @property
    def _lock_pid_file(self):
        return self._lock_folder.parent / 'lock-pid'

    def _write_lock_pid(self):
        if self._lock_pid_file.exists():
            raise FileExistsError(self._lock_pid_file)

        p = psutil.Process()
        data = f'{p.pid},{p._create_time}'

        with open(self._lock_pid_file, 'wt') as f:
            f.write(data)

    @property
    def _lock_pidinfo(self):
        if self._lock_pid_file.exists():
            with open(self._lock_pid_file, 'rt') as f:
                data = f.read()
                spid, screate_time = data.split(',')
                pid = int(spid)
                create_time = float(screate_time)
                return pid, create_time
        else:
            return None, None

    def _locking_process_dead(self):
        pid, create_time = self._lock_pidinfo
        if pid is None:
            # pidinfo file doesn't exist so the lock folder
            # is not handled by us
            return True

        if not psutil.pid_exists(pid):
            return True

        p = psutil.Process(pid)
        return p._create_time != create_time

    def _unlock_pid(self):
        self._lock_pid_file.unlink()

    def _lock_folder_lsu(self):
        paths = sorted(self._lock_folder.iterdir())
        if paths:
            last = paths[-1]
            more_annos, last_sync_updated = self.get_annos_from_file(last)
            return last_sync_updated

    def _get_annos_from_folder(self):
        new_annos = []
        last_sync_updated = None
        for jpath in sorted(self._lock_folder.iterdir()):
            more_annos, last_sync_updated = self.get_annos_from_file(jpath)
            new_annos.extend(more_annos)

        return new_annos, last_sync_updated

    def _lock_folder_to_json(self, annos):
        new_annos, lsu = self._get_annos_from_folder()
        if new_annos:
            self._merge_new_annos(annos, new_annos)
            self.memoize_annos(annos)

        return new_annos

    def _merge_new_annos(self, annos, new_annos):
        new_ids = set(a.id for a in new_annos)
        n_updated = 0
        for anno in tuple(annos):
            if anno.id in new_ids:
                annos.remove(anno)  # FIXME stale data in helper data structures
                n_updated += 1

        annos.extend(new_annos)
        log.info(f'added {len(new_annos) - n_updated} new annotations')
        if n_updated:
            log.info(f'updated {n_updated} annotations')

    def memoize_annos(self, annos):
        # FIXME if there are multiple ws listeners we will have race conditions?
        if self.memoization_file is not None:
            msg = ('annos updated, memoizing new version with, '
                   f'{len(annos)} members')
            log.info(msg)
            do_chmod = False
            if not self.memoization_file.exists():
                do_chmod = True
                if not self.memoization_file.parent.exists():
                    self.memoization_file.parent.mkdir()

            if do_chmod:
                # always touch and chmod before writing
                # so that there is no time at which a file
                # with data can exist with the wrong permission
                self.memoization_file.touch()
                self.memoization_file.chmod(0o600)

            with open(self.memoization_file, 'wt') as f:
                lsu = annos[-1].updated if annos else None
                alsu = annos, lsu
                json.dump(alsu, f, cls=JEncode)

        else:
            log.info(f'No memoization file, not saving.')

    def get_annos(self):
        annos, last_sync_updated = self.get_annos_from_file()
        new_annos = self._stream_annos_from_api(annos, last_sync_updated)
        return annos

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
    # XXX design flaw, group is not required at this point, should be passed for operations
    # a default_group could be set ... the issue is deep and pervasive though because the
    # group id is expected all over the fucking place
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
            headers = {'Authorization': 'Bearer ' + self.token,
                       'Content-Type': 'application/json;charset=utf-8'}
            r = requests.get(query_url, headers=headers)
            obj = r.json()
            if r.ok:
                return obj
            else:
                raise NotOkError(f'response was not ok! {r.reason} {obj}', r)

        except requests.exceptions.SSLError as e:
            if self.ssl_retry < 5:
                self.ssl_retry += 1
                log.error(f'Ssl error at level {self.ssl_retry} retrying....')
                return self.authenticated_api_query(query_url)
            else:
                self.ssl_retry = 0
                log.error(e)
                return {'ERROR': True, 'rows': tuple()}
        except KeyboardInterrupt:
            raise
        except BaseException as e:
            log.exception(e)
            #print('Request, status code:', r.status_code)  # this causes more errors...
            return {'ERROR': True, 'rows': tuple()}

    def make_annotation_payload_with_target_using_only_text_quote(
            self, url, prefix, exact, suffix, text, tags, document, extra):
        """Create JSON payload for API call."""
        if exact is None:
            target = [{'source': url}]
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
        if text is None:
            text = ''
        if tags is None:
            tags = []
        if document is None:
            document = {}
        payload = {
            "uri": url,
            "user": 'acct:' + self.username + '@hypothes.is',
            "permissions": self.permissions,
            "group": self.group,
            "target": target,
            "tags": tags,
            "text": text,
            "document": document,
        }

        if extra is not None:
            payload['extra'] = extra

        return payload

    def create_annotation_with_target_using_only_text_quote(
            self, url=None, prefix=None, exact=None, suffix=None, text=None,
            tags=None, tag_prefix=None, document=None, extra=None):
        """Call API with token and payload, create annotation (using only text quote)"""
        payload = self.make_annotation_payload_with_target_using_only_text_quote(
            url, prefix, exact, suffix, text, tags, document, extra)
        try:
            r = self.post_annotation(payload)
        except KeyboardInterrupt:
            raise
        except BaseException as e:
            log.error(payload)
            log.exception(e)
            # if we get here someone probably ran the
            # bookmarklet from firefox or the like
            r = None
        return r

    def head_annotation(self, id):
        # used as a 'kind' way to look for deleted annotations
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Content-Type': 'application/json;charset=utf-8'}
        r = requests.head(self.api_url + '/annotations/' + id, headers=headers)
        return r

    def get_annotation(self, id):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Content-Type': 'application/json;charset=utf-8'}
        r = requests.get(self.api_url + '/annotations/' + id, headers=headers)
        return r

    def post_annotation(self, payload):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Content-Type': 'application/json;charset=utf-8'}
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.post(self.api_url + '/annotations',
                          headers=headers,
                          data=data.encode('utf-8'))
        return r

    def patch_annotation(self, id, payload):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Content-Type': 'application/json;charset=utf-8'}
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.patch(self.api_url + '/annotations/' + id,
                           headers=headers,
                           data=data.encode('utf-8'))
        return r

    def delete_annotation(self, id):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Content-Type': 'application/json;charset=utf-8'}
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
            if lr == 0:
                return

            stop = None
            if max_results:
                if nresults >= max_results:
                    stop = max_results - nresults + lr

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
            log.info(f'searching after {search_after}')

    def search_url(self, **params):
        return (self
                .search_url_template
                .format(query=(urlencode(params, True)
                               .replace('=', '%3A'))))  # = > :

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

    def batch_update(self, function, *ids, pretend=True):
        """ apply a function a set of annotations from their ids
            and patch the changes back to the remote
            pretend is set to True by default so that you can test the output
            before shooting yourself in the foot """
        # this is a friendly function that does sequential requests
        # if you want something e.g. with Async/deferred, don't use this

        if pretend:
            yield from ((a, function(a)) for id in ids
                        for a in (self.get_annotation(id).json(),))

        else:
            for id in ids:
                resp = self.get_annotation(id)
                blob = resp.json()
                updated = function(blob)
                yield blob, self.patch_annotation(id, updated)


class HypAnnoId(str):  # TODO derive from Identifer ...

    @property
    def iri(self):  # FIXME share or html ...
        return f'https://hyp.is/{self}'

    shareLink = iri

    @property
    def htmlLink(self):
        return f'https://hypothes.is/a/{self}'

    def compact(self, namespace_manager_ontcuries_localnamemanager_etc):
        """ given a compacting function, ball yourself up and put a bow on ya """
        # compact using rules from one of many, many implementations
        # of local <-> global name mapping
        # ids should retain the compact representation that they
        # were originally defined with
        # it seems simple enough to allow many other representations to
        # be generated by simply telling the identifer to ball itself
        # up according to the rules that it was passed ...
        # since the calling context clearly cares to have it shortened
        # according to those rules rathern than the original rules
        compactor = namespace_manager_ontcuries_localnamemanager_etc
        return compactor(self.iri)

    @property
    def curie(self):
        # the curie by convention
        return 'hyp:' + self  # FIXME need a better way ...

    def htmlCurie(self):
        return 'hypa:' + self  # FIXME not sure if correct ...

    @property
    def _asInstrumented(self):
        return Annotation(self, autofetch=False)  # FIXME distinguish/differentiate Anno vs HypAnno

    # FIXME decide on whether instrumentation should be a property or method
    # Given that in theory we can have an additional layer of not going to network
    # instantly by setting autofetch to False, the property approach might be ok
    # HOWEVER using a property like this makes it difficult to use asInstrumented
    # in Async/deferred to fetch a bunch of remote data in one shot
    # both variants are here, but I'm leaning toward the function -> autofetch
    # version, which will probably also be a better approach for OntId.asTerm as well...
    # patterns like Async(rate=lol)(deferred(id.asInstrumented)() for id in ids)
    # and Async(rate=lol)(deferred(AltAnnoImplementation)(id) for id in ids) both work
    # and make it easier to manage the balance between default and alternate remote stores

    def asInstrumented(self):
        return Annotation(self)  # FIXME distinguish/differentiate Anno vs HypAnno

    def __repr__(self):
        return f'{self.__class__.__name__}({self!r})'


class Annotation:
    """ a better object implementation for annotations needs to be merged with
        the HypothesisAnnotation implementation
    """

    immutable_fields = [
        'target',  # the target uri
        'exact',
    ]

    @classmethod
    def setup(cls, store=HypothesisUtils(username=username, group=group, token=api_token)):
        cls.store = store

    @classmethod
    def fromJson(cls, json):
        self = object.__new__(cls)  # skip the usual init process
        self._prior_versions = []  # FIXME as opposed @field.setter always returning a new object ...
        self._last_external = json  # the last thing we got from somewhere else
        self._json = json
        if 'id' in json:
            self.identifier = json['id']
        else:
            self.identifier = None

        return self

    def __init__(self, identifier, autofetch=True):
        self.identifier = identifier
        # FIXME the ability to have multiple stores that
        # cross reference eachother for robustness ...
        # 'this annotation can be found in x, y, and z'
        # stores under 'a, b, and c' identifiers respectively
        # for stuff like this having the store be able to
        # search by hash would be great ...
        if autofetch:
            self.data()

    def _update_path(self, path, value):
        # TODO ...
        # a use case for adops ... ?
        current_value = getpath(self._json)
        if current_value != value:
            old = self._json
            new = deepcopy(self._json)
            setpath(new, value)
            self._prior_versions.append(old)
            self._json = new

    def data(self, _refresh_cache=False):
        # a bit overkill given how small most annotations are
        # but, no harm in matching the pattern we use everywhere
        # else, and setting autofetch = True in init so that
        # there is the option to disable for a potential
        # bulk request ...

        # FIXME autocache so that data always returns the
        # latest retrieved raw value? I think it should cache
        # and a new object should be returned for new versions
        # so that at least in this system the history of changes
        # can be preserved, even if the identifier stays the same
        # we apply the versioned doi approach where unqualified we
        # resolve to the usual landing page, and if you want a more
        # granular version then I think the updated datetime is the
        # simplest differentiator, primary key on id + updated ...
        # to allow the /{id}/version/{updated} pattern ...

        # the way to make the caching efficient is to pull the group
        # annotations, and then always pull from the group cache
        # until the next time _refresh_cache=True is called
        # then a bulk update can be issued, still issues with
        # syncing since we would need an endpoint that could
        # request multiple annotation bodies at the same time
        resp = self.store.get_annotation(self.identifier)
        self.headers = resp.headers
        self._json = resp.json()
        self._last_external = self._json
        return self._json

    def send(self, store=None):
        # FIXME post/patch/update send my data to the server please
        # send ..., yes send, ...
        # based on the remote service the annotation should just do
        # the right thing, and frankly an append only store just needs
        # to know the id
        if self.identifier is None:
            resp = self.store.post_annotation(self._json)
            blob = resp.json()
            self.identifier = blob['id']

        elif self._last_external != self._json:
            resp = self.store.patch_annotation(self._json)

        else:
            log.warning(f'Data for {self.identifier} '
                        'has not changed, not sending.')

    def diff(self, other=None):
        raise NotImplementedError('since we are keeping prior versions ...')

    def __hash__(self):
        return hash((self.__class__, self.id, self.updated))


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
        return (self._row['user']
                .replace('acct:', '')
                .replace('@hypothes.is', ''))

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

        title = title.replace('"', "'")
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

        uri = (uri
               .replace('https://via.hypothes.is/h/', '')
               .replace('https://via.hypothes.is/', ''))

        if uri.startswith('urn:x-pdf'):
            document = self.document
            for link in self.links:
                uri = link['href']
                if not uri.encode('utf-8').startswith(b'urn:'):
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

    def parent(self, pool):
        try:
            return next(pool.getParents(self))
        except StopIteration:
            pass

    def is_annotation(self):
        for t in self.targets:
            if 'selector' in t:
                return True

        return False

    def is_reply(self):
        # at some point annotations should have references
        # so we test whether it is an annotation first
        return bool(self.references) and not self.is_annotation()

    def is_page_note(self):
        return not (self.is_annotation() or self.is_reply())

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
            if 'type' in selector and selector['type'] == type and len(selector) > 1:
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
    def permissions(self): return {k:v for k, v in self._row['permissions'].items()}

    def __eq__(self, other):
        # text and tags can change, if exact changes then the id will also change
        return (self.id == other.id and
                self.text == other.text and
                set(self.tags) == set(other.tags) and
                self.updated == other.updated)

    def __hash__(self):
        # FIXME why do we need self.text if we have updated?
        return hash((self.id, self.text, self.updated))

    def __lt__(self, other):
        return self.updated < other.updated

    def __gt__(self, other):
        return not self.__lt__(other)


class AnnotationPool:
    """ classic object container class """
    def __init__(self, annos=None, cls=HypothesisAnnotation):
        self._index = {a.id:a for a in annos}

        dd = defaultdict(list)
        for a in annos:
            for ref in a.references:
                try:
                    parent = self._index[ref]
                    dd[parent].append(a)
                except KeyError as e:
                    log.warning(f'dangling reply {a}')

        self._replies_index = dict(dd)
        self._replies = {}  # XXX see if we can remove this (used in getParents)

        if annos is None:
            annos = []

        self._annos = annos

    def add(self, annos):
        # TODO update self._index etc.
        self._annos.extend(annos)
        for a in annos:
            # FIXME warn on collision?
            self._index[a.id] = a
            for ref in a.references:
                parent = self._index[ref]
                if parent not in self._replies_index:
                    self._replies_index[parent] = []

                self._replies_index[parent].append(a)

    def replies(self, id_annotation):
        a = self.byId(id_annotation)
        if a in self._replies_index:
            yield from self._replies_index[a]

    def byId(self, id_annotation):
        try:
            return self._index[id_annotation]
        except KeyError as e:
            pass

    def getParents(self, anno):
        # TODO consider auto retrieve on missing?
        if not anno.references:
            return None
        else:
            # go backward to get the direct parent first, slower for shareLink but ok
            for parent_id in anno.references[::-1]:
                parent = self.byId(parent_id)
                if parent is not None:
                    if parent.id not in self._replies:
                        self._replies[parent.id] = set()
                    self._replies[parent.id].add(self)
                    yield parent


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
        with referential structure an pretty printing.
        XXX BIG WARNING HERE: you can only use ALL subclasses of HypothesisHelper
        XXX for a single group of annotations at a time otherwise things will go
        XXX completely haywire, transition to use AnnotationPool if at all possible
    """
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
            msg = (f'{cls.__name__}.objects has not been '
                   'populated with annotations yet!')
            raise Warning(msg) from e

    @classmethod
    def byTags(cls, *tags):
        if cls._done_loading:  # TODO maybe better than done loading is 'consistent'?
            if not cls._tagIndex:
                log.debug('populating tags')
                # FIXME extremely inefficient on update
                # and we want this to update as replies appear
                # not all at once...
                # FIXME this does not update if new annos are added on the fly!
                [obj.populateTags() for obj in cls.objects.values()]

            return sorted(set.intersection(*(cls._tagIndex[tag] for tag in tags)))
        else:
            log.warning('attempted to search by tags before done loading')

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
        log.debug(f'Removing {self._repr} from {len(self._remove_self_from)} tag sets')
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

    @classmethod
    def reset(cls, reset_annos_dict=False):
        """ explicitly reset the class state removing _annos_list and _annos
            normally this should be called before the first time a program
            populates annotations so that any persistent state from another
            program is removed unfriendly if they need to coexist, but for that
            to actually work this whole thing needs a rewrite to have explicit
            representation of annotation groups

            XXX WARNING this also resets ALL PARENT CLASSES
        """

        cls.objects = {}
        cls._tagIndex = {}
        cls._replies = {}
        cls.reprReplies = True
        cls._embedded = False
        cls._done_loading = False
        if reset_annos_dict:
            HypothesisHelper._annos = {}
            HypothesisHelper._index = {}
            # DO NOT RESET THIS (under normal circumstances)

        # the risk of staleness is worth it since we have
        # already worked through most of the possible issues
        # around things going stale for that
        # FIXME yes, yet another reason to switch to explicit
        # representation of in memory annotation stores
        # NOTE if you are swapping out a set of annos for a
        # subset of those annos, then definitely reset this

        for a in ('_annos_list',):
            if hasattr(cls, a):
                # cannot just use delattr here because
                # the annos list might be on a parent class
                # which is bad ... because this will reset
                # ALL the parent classes as well, which is ...
                # a result of the bad design of hypothesis helper
                # NOTE we still have to delattr here because
                # _annos_list IS set per class, but may also be
                # set on parents >_< (screaming)
                try:
                    delattr(cls, a)
                except AttributeError:  # LOL PYTHON
                    pass

                # FIXME WARNING EVIL SIDE EFFECTS ON OTHER CLASSES
                # YOU WERE WARNED ABOVE
                for pcls in cls.mro()[1:]:
                    if hasattr(pcls, '_annos_list'):
                        try:
                            delattr(pcls, '_annos_list')
                        except AttributeError:
                            pass

    def __new__(cls, anno, annos):
        if not hasattr(cls, '_annos_list'):
            cls._annos_list = annos
        elif cls._annos_list is not annos:  # FIXME STOP implement a real annos (SyncList) class FFS
            # hack to fix O(n ** 2) behavior or worse behavior
            # when readding the same set of annos over and over
            # I'm pretty sure that there is pathalogical behavior
            # hiding here because of the expectation that cls._annos_list is annos
            # for sync purposes ... sigh bad design coming back to haunt me again
            # having subclasses of HypothesisHelper act as singletons seems like
            # a good idea but eventually it will bite you
            sal = set(cls._annos_list)
            sa = set(annos)
            added = sa - sal
            removed = sal - sa
            if added:
                new = [a for a in annos if a in added]
                cls._annos_list.extend(new)

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
                msg = ('it seems you have duplicate entries for annos: '
                       f'{len(cls._annos)} != {len(annos)}')
                logd.critical(msg)
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
            #breakpoint()
            log.critical(str(self._tagIndex))
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
                        logd.warning(f"Problem in {self.shareLink} {self.classn}.byId('{self.id}')")
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
            log.warning('Not done loading annos, you will be missing references!')
            return set()

    def __eq__(self, other):
        return (type(self) == type(other) and
                self.id == other.id and
                self.text == other.text and
                set(self.tags) == set(other.tags) and
                self.updated == other.updated)

    def __hash__(self):
        return hash((self.__class__.__name__, self.id, self.updated))

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
        if html:
            link = f'<a href="{link}">{link}</a>'
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
