import re
from setuptools import setup


def find_version(filename):
    _version_re = re.compile(r"__version__ = '(.*)'")
    for line in open(filename):
        version_match = _version_re.match(line)
        if version_match:
            return version_match.group(1)


__version__ = find_version('hyputils/__init__.py')

with open('README.md', 'rt') as f:
    long_description = f.read()

tests_memex_require = ['bleach',
                       'jsonschema',
                       'mistune',
                       "psycopg2; implementation_name != 'pypy'",
                       "psycopg2cffi; implementation_name == 'pypy'",
                       'python-slugify',
                       'sqlalchemy',
                       'webob']
tests_require = ['factory-boy', 'pytest'] + tests_memex_require
setup(name='hyputils',
      version=__version__,
      description='Python utilities for the Hypothes.is REST api and websocket interface',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/tgbugs/hyputils',
      author='Tom Gillespie',
      author_email='tgbugs@gmail.com',
      license='MIT',
      classifiers=[
          'Development Status :: 4 - Beta',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10',
      ],
      keywords='hypothesis hypothes.is web annotation',
      packages=['hyputils',
                'hyputils.memex',
                'hyputils.memex.db',
                'hyputils.memex.models',
                'hyputils.memex.schemas',
                'hyputils.memex.util',],
      python_requires='>=3.6',
      tests_require=tests_require,
      install_requires=[
          'appdirs',
          'certifi',
          'psutil',
          'requests',
          'websockets',
      ],
      extras_require={'dev': ['pytest-cov', 'wheel'],
                      'memex':['python-dateutil'] + tests_memex_require,
                      'test': tests_require,
                      'zdesk': ['pyyaml', 'zdesk'],
                     },
      entry_points={
          'console_scripts': [
          ],
      },
     )
