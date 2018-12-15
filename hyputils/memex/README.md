# memex
A minimal subest of the hypothes.is h server codebase

# Setup
This section will be updated when an abstracted setup for memex
is created from the scibot setup instructions.

An example of how to set up a database for memex can be seen in the
[scibot setup instructions](https://github.com/SciCrunch/scibot/blob/master/docs/setup.md).
The relevant steps when working with a database cluster are as follows.
1. Create the database as postgres
https://github.com/SciCrunch/scibot/blob/master/bin/scibot-dbsetup
2. Pass an sqlalchemy engine to `hyputils.memex.db.init` to create tables etc.
https://github.com/SciCrunch/scibot/blob/ee90c73ce41e6697e97c3faa7b187a2b333f5178/scibot/db.py#L42

# Background
## Introduction
Memex is an extracted subset of the hypothesis server codebase.

Its objective is to be frontend independent and provide the core
functionality for storing web annotations in a relation database
and validating their structure on ingest.

The parts that are retained pretain to annotations, documents, users,
and groups, with room for further slimming the datamodel.

## Provenance
Starting at [hyputils](https://github.com/tgbugs/hyputils) commit 7306c3db095335e616c2c9cfc536f6f237f05156
files from the [h](https://github.com/hypothesis/h) codebase at commit 68d82e20b116b94f6b7d54718a25f9f4118a80db
were added. [import.sh](import.sh) has an accounting of most of those files, but a
few may have slipped through. The h codebase is licensed as BSD2 (see
https://github.com/hypothesis/h/blob/68d82e20b116b94f6b7d54718a25f9f4118a80db/LICENSE#L1-L21
and https://github.com/hypothesis/h/blob/68d82e20b116b94f6b7d54718a25f9f4118a80db/README.rst#license
for more details). Merge commits from the memex branch into master should list the
commit on h from which any changes were sourced.

## Changes
The file structure from h has been preserved with the slight change that memex
is a submodules of hyputils so it is one node further away from `test/memex` than
in the h codebase.

Aside from reducing the size of the data model the primary objective of memex
is to decouple the database related code in h from the api, search, frontend, etc.
Principally, this takes the form of removing various pyramid related dependencies.

Group and user acl related code has been kept around as code extracted from pyramid
and lives in [security.py](security.py). This code may be reworked to further decouple
the core database from other implementation details.

## Synchronization
Ideally some of the decoupling can be pushed back upstream (see https://github.com/tgbugs/h/tree/independent-db
for some of my work to decouple the database inside h). Most of the changes needed
to allow importing only a subset of the h models and json schemas without pulling
in search and pyramid related code just require moving those functions and classes
to their own files and modifying imports accordingly.

The easiest way to see which code needs to be moved elsewhere is to run import.sh
(e.g. with h at commit 68d82e20b116b94f6b7d54718a25f9f4118a80db) and look at which
code is added back (e.g. around hyputils beee2b43e91ec55e8c0a97c1ae11b0751f0926cd).

In some cases the simplified data model means that h code cannot be reused without
restructuring the h model hierarchy to use stripped down base clases.

Pulling in changes from upstream can be accomplished by running import.sh and then
re-removing the unneeded sections. At some point it might be possible to automate
some of these changes.
