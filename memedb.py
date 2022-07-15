import sqlite3
import time

class MemeDb:
    def __init__(self, dbfile):
        conn = sqlite3.connect(dbfile)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        self.c = conn.cursor()
        self.createTables()

    def createTables(self):
        self.c.execute('''CREATE TABLE IF NOT EXISTS matches
            (subreddit TEXT, key TEXT, trigger TEXT, ext TEXT, url TEXT, thread_id TEXT, trigger_id TEXT, was_reply INTEGER, ts INTEGER)''')

        self.c.execute('''CREATE TABLE IF NOT EXISTS comments
            (cid TEXT, text TEXT, ts INTEGER)''')
        self.c.execute('''CREATE INDEX IF NOT EXISTS cd_cid ON comments(cid)''')

        self.c.execute('''CREATE TABLE IF NOT EXISTS candidates
            (key TEXT, ext TEXT, cid TEXT, ts INTEGER)''')
        self.c.execute('''CREATE INDEX IF NOT EXISTS key_ext ON candidates(key, ext)''')

    def insertWithTs(self, query, params, ts=None):
        if not ts:
            ts = time.time()
        return self.c.execute(query, params + (ts,))

    def addMatch(self, comment, key, ext, ts, imagekey, url):
        return self.insertWithTs(
            '''INSERT INTO matches(subreddit, thread_id, key, trigger, ext, url, trigger_id, was_reply, ts) VALUES(?,?,?,?,?,?,?,?,?)''',
            (comment.subreddit.display_name, comment.link_id, imagekey, key, ext, url, comment.id, 0),
            ts
        )

    def addCandidate(self, comment, key, ext, ts):
        return self.insertWithTs(
            '''INSERT INTO candidates(key, ext, cid, ts) VALUES(?,?,?,?)''',
            (key, ext, comment.id),
            ts
        )

    def addComment(self, comment, message, ts=None):
        return self.insertWithTs(
            '''INSERT INTO comments(cid, text, ts) VALUES(?,?,?)''',
            (comment.id, message),
            ts
        )
