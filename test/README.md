Reminder to use the api-test group to run the tests in this folder.
If you ar running tests manually you will need to point to a postgres instance.
For example
``` bash
TEST_DATABASE_URL="postgresql://postgres@localhost:54321/htest" PYTHONWARNINGS=ignore pytest test
```
