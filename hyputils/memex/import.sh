H=${HOME}/git/h/h
M=${HOME}/git/hyputils/hyputils/memex
HT=${HOME}/git/h/tests/h
MT=${HOME}/git/hyputils/test/memex

mkdir ${M}/db
mkdir ${M}/models
mkdir ${M}/schemas
mkdir ${M}/util

mkdir ${MT}/db
mkdir ${MT}/models
mkdir ${MT}/schemas
mkdir ${MT}/util

cpfile () {
    FILEPATH=${1}
    cp ${H}/${FILEPATH} ${M}/${FILEPATH}
}

cptest () {
    FILEPATH=${1}
    cp ${HT}/${FILEPATH} ${MT}/${FILEPATH}
}

# source code
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
cpfile util/document_claims.py
cpfile util/group.py
cpfile util/markdown.py
cpfile util/uri.py
cpfile util/user.py

# tests

cptest db/__init__.py
cptest db/types_test.py

cptest models/annotation_test.py
cptest models/document_test.py
cptest models/group_test.py
cptest models/organization_test.py
cptest models/user_identity_test.py
cptest models/user_test.py

cptest schemas/__init__.py
cptest schemas/annotation_test.py
cptest schemas/base_test.py

cptest util/__init__.py
cptest util/document_claims_test.py
cptest util/markdown_test.py
cptest util/uri_test.py
cptest util/user_test.py
