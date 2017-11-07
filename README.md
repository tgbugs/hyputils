# hyputiles
python utilites for working with the hypothes.is api and websocket interface

## Dependencies
beautifulsoup
certifi
pyontutils
requests
robobrowser
websockets
zdesk

## Config files
`zendeskinfo.yaml` should contain
```
zdesk_url: https://yoururl.zendesk.com
zdesk_email: your@email.com
zdesk_password: your_token_or_password
zdesk_token: True

```
# Fun!
If you never modify your annotations, but instead
only add new replies to modify them you can view a
snapshot of the state of your annotation work and
understanding at time T by simply excluding all
anotations with updated > T!
