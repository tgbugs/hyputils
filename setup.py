from setuptools import setup

setup(name='hyputils',
      version='0.0.2',
      description='Python utilities for the Hypothes.is REST api and websocket interface',
      long_description=' ',
      url='https://github.com/tgbugs/hyputils',
      author='Tom Gillespie',
      author_email='tgbugs@gmail.com',
      license='MIT',
      classifiers=[],
      keywords='hypothesis hypothes.is web annotation',
      packages=['hyputils'],
      python_requires='>=3.6',
      install_requires=[
          'certifi',
          'requests',
          'robobrowser',
          'websockets',
      ],
      extras_require={'dev':['yaml', 'zdesk']},
      entry_points={
          'console_scripts': [
          ],
      },
     )
