mkdir db
mkdir models
mkdir schemas
mkdir util
H=${HOME}/git/h/h
M=${HOME}/git/hyputils/hyputils/memex

cpfile () {
    FILEPATH=${1}
    cp ${H}/${FILEPATH} ${M}/${FILEPATH}
}
cpfile _compat.py
cpfile pubid.py

cpfile db/__init__.py
cpfile db/mixins.py
cpfile db/types.py

cpfile models/__init__.py
cpfile models/annotation.py
cpfile models/document.py
cpfile models/group.py
cpfile models/organization.py
cpfile models/user.py
cpfile models/user_identity.py

cpfile schemas/__init__.py
cpfile schemas/annotation.py
cpfile schemas/base.py

cpfile util/__init__.py
cpfile util/uri.py
cpfile util/user.py
cpfile util/markdown.py
