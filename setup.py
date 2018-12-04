from setuptools import setup

with open('README.md', 'rt') as f:
    long_description = f.read()

setup(name='hyputils',
      version='0.0.2',
      description='Python utilities for the Hypothes.is REST api and websocket interface',
      long_description=long_description,
      long_description_content_type='text/markdown',
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
