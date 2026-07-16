"""This one is like the mutex lock in the os. To prevent the race condition we use the lock so no 2 quries can 
access the same resource at the same time. This one will keep the track of the locks so they might not be slowing down 
the database"""

from pydantic import BaseModel # type:ignore

class LockStats(BaseModel):
    """
    Database lock information.
    """

    pid: int

    lock_type: str # is it blocking a sigle row or the entire table

    relation: str | None = None # the name of the table that is being locked

    mode: str # the type of lock that is being used. It can be AccessShareLock, RowExclusiveLock, etc.

    granted: bool # has the process acquired the lock or is it waiting for it to be released