H=${HOME}/git/h/h
M=${HOME}/git/hyputils/hyputils/memex
HT=${HOME}/git/h/tests/h
MT=${HOME}/git/hyputils/test/memex
HTC=${HOME}/git/h/tests/common
MTC=${HOME}/git/hyputils/test/common

mkdir ${M}/db
mkdir ${M}/models
mkdir ${M}/schemas
mkdir ${M}/util

mkdir ${MTC}/factories

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

cpcommon () {
    FILEPATH=${1}
    cp ${HTC}/${FILEPATH} ${MTC}/${FILEPATH}
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

# test common

cpcommon __init__.py
cpcommon matchers.py

cpcommon factories/__init__.py
cpcommon factories/base.py
cpcommon factories/annotation.py
cpcommon factories/document.py
cpcommon factories/group.py
cpcommon factories/organization.py
cpcommon factories/user.py
cpcommon factories/user_identity.py

# tests

cptest conftest.py

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

# update imports
# sed -i 's/\(from\|import\) h\(\.\|\ \)/\1 hyputils.memex\2/' {,*/}*.py
# sed -i 's/"h\./"hyputils.memex./' {,*/}*.py
