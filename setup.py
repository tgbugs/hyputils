from setuptools import setup

with open('README.md', 'rt') as f:
    long_description = f.read()

tests_require = ['factory-boy', 'mock', 'pytest', 'pytest-cov']
setup(name='hyputils',
      version='0.0.3',
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
      extras_require={'zdesk': ['pyyaml', 'zdesk'],
                      'test': tests_require,
                      'memex':['bleach',
                               'jsonschema',
                               'mistune',
                               'psycopg2',
                               'python-slugify',
                               'sqlalchemy',
                               'webob',
                              ]
                     },
      entry_points={
          'console_scripts': [
          ],
      },
     )
