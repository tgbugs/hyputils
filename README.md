# hyputils
[![PyPI version](https://badge.fury.io/py/hyputils.svg)](https://pypi.org/project/hyputils/)
[![Build Status](https://travis-ci.org/tgbugs/hyputils.svg?branch=master)](https://travis-ci.org/tgbugs/hyputils)
[![Coverage Status](https://coveralls.io/repos/github/tgbugs/hyputils/badge.svg?branch=master)](https://coveralls.io/github/tgbugs/hyputils?branch=master)

python utilities for working with the hypothes.is api and websocket interface

## Config files
`zendeskinfo.yaml` should contain
```
zdesk_url: https://yoururl.zendesk.com
zdesk_email: your@email.com
zdesk_password: your_token_or_password
zdesk_token: True

```

## Usage
hyputils checks the following enviornment variables
1. `HYP_API_TOKEN` is your api token.
2. `HYP_USERNAME` is your username (not strictly required).
3. `HYP_GROUP` is the 8 char group identifier.

# Fun!
If you never modify your annotations, but instead
only add new replies to modify them you can view a
snapshot of the state of your annotation work and
understanding at time T by simply excluding all
anotations with updated > T!
