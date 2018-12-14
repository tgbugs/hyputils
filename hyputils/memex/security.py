class AllPermissionsList(object):
    """ Stand in 'permission list' to represent all permissions """
    def __iter__(self):
        return ()
    def __contains__(self, other):
        return True
    def __eq__(self, other):
        return isinstance(other, self.__class__)


ALL_PERMISSIONS = AllPermissionsList()


class security:
    """ local version of pyramid security object """
    Allow = 'Allow'
    Everyone = 'system.Everyone'
    DENY_ALL = ('Deny', 'system.Everyone', AllPermissionsList())
