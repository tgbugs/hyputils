import sys

__need_cffi = hasattr(sys, 'pypy_version_info')
__dialect = 'psycopg2cffi' if __need_cffi else 'psycopg2'


def database_url(url, dialect=__dialect, need_cffi=__need_cffi):
    """Parse a string as a Heroku-style database URL."""
    # Heroku database URLs start with postgres://, which is an old and
    # deprecated dialect as far as sqlalchemy is concerned. We upgrade this
    # to postgresql+psycopg2 by default.
    if url.startswith("postgres://"):
        url = f"postgresql+{dialect}://" + url[len("postgres://") :]
    elif need_cffi:
        prefix, suffix = url.split('://', 1)
        url = f"postgresql+{dialect}://" + suffix

    return url
