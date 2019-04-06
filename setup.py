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

tests_require = ['factory-boy', 'mock', 'pytest', 'pytest-runner']
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
      ],
      keywords='hypothesis hypothes.is web annotation',
      packages=['hyputils'],
      python_requires='>=3.6',
      tests_require=tests_require,
      install_requires=[
          'certifi',
          'requests',
          'websockets',
      ],
      extras_require={'dev': ['pytest-cov', 'wheel'],
                      'memex':['bleach',
                               'python-dateutil',
                               'jsonschema',
                               'mistune',
                               'psycopg2',
                               'python-slugify',
                               'sqlalchemy',
                               'webob',
                              ],
                      'test': tests_require,
                      'zdesk': ['pyyaml', 'zdesk'],
                     },
      entry_points={
          'console_scripts': [
          ],
      },
     )
