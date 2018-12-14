class AllPermissionsList(object):
    """ Stand in 'permission list' to represent all permissions """
    def __iter__(self):
        return ()
    def __contains__(self, other):
        return True
    def __eq__(self, other):
        return isinstance(other, self.__class__)


ALL_PERMISSIONS = AllPermissionsList()


def is_nonstr_iter(v):
    """ from pyramid.compat """
    if isinstance(v, str):
        return False
    return hasattr(v, '__iter__')


def lineage(resource):
    """ from pyramid.location """
    while resource is not None:
        yield resource
        try:
            resource = resource.__parent__
        except AttributeError:
            resource = None


class security:
    """ local version of pyramid security object """
    Allow = 'Allow'
    Deny = 'Deny'
    Authenticated = 'system.Authenticated'
    Everyone = 'system.Everyone'
    DENY_ALL = ('Deny', 'system.Everyone', AllPermissionsList())
    ACLDenied = 0
    ACLAllowed = 1
    class ACLAuthorizationPolicy(object):
        """ stripped down acl auth policy """

        @staticmethod
        def permits(context, principals, permission):

            acl = '<No ACL found on any object in resource lineage>'

            for location in lineage(context):
                try:
                    acl = location.__acl__
                except AttributeError:
                    continue

                if acl and callable(acl):
                    acl = acl()

                for ace in acl:
                    ace_action, ace_principal, ace_permissions = ace
                    if ace_principal in principals:
                        if not is_nonstr_iter(ace_permissions):
                            ace_permissions = [ace_permissions]
                        if permission in ace_permissions:
                            if ace_action == security.Allow:
                                return security.ACLAllowed
                            else:
                                return security.ACLDenied

            return security.ACLDenied

        def principals_allowed_by_permission(self, context, permission):
            allowed = set()

            for location in reversed(list(lineage(context))):
                # NB: we're walking *up* the object graph from the root
                try:
                    acl = location.__acl__
                except AttributeError:
                    continue

                allowed_here = set()
                denied_here = set()

                if acl and callable(acl):
                    acl = acl()

                for ace_action, ace_principal, ace_permissions in acl:
                    if not is_nonstr_iter(ace_permissions):
                        ace_permissions = [ace_permissions]
                    if (ace_action == security.Allow) and (permission in ace_permissions):
                        if not ace_principal in denied_here:
                            allowed_here.add(ace_principal)
                    if (ace_action == security.Deny) and (permission in ace_permissions):
                            denied_here.add(ace_principal)
                            if ace_principal == security.Everyone:
                                # clear the entire allowed set, as we've hit a
                                # deny of Everyone ala (Deny, Everyone, ALL)
                                allowed = set()
                                break
                            elif ace_principal in allowed:
                                allowed.remove(ace_principal)

                allowed.update(allowed_here)

            return allowed
