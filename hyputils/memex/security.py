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
    if isinstance(v, str):
        return False
    return hasattr(v, '__iter__')


class security:
    """ local version of pyramid security object """
    Allow = 'Allow'
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
                            if ace_action == Allow:
                                return security.ACLAllowed
                            else:
                                return security.ACLDenied

            return security.ACLDenied
