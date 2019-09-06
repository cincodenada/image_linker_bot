#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import sqlite3
import time

class CommentStore():
  def __init__(self, dbfilename):
    self.conn = sqlite3.connect(dbfilename)
    self.conn.row_factory = sqlite3.Row
    self.conn.isolation_level = None
    self.c = self.conn.cursor()

    self.c.execute('''CREATE TABLE IF NOT EXISTS inbox
        (tid TEXT, subject TEXT, body TEXT, sender TEXT, sent INTEGER, seen INTEGER, parent_id TEXT)''')
    self.c.execute('''CREATE INDEX IF NOT EXISTS inbox_seen ON inbox(seen)''')
    self.c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS inbox_id ON inbox(tid)''')

  def add_message(self, m):
    try:
      if(m.subreddit):
        self.c.execute('''INSERT INTO inbox(tid, subject, body, sender, sent, seen, parent_id) VALUES(?,?,?,?,?,?,?)''',
            (m.name, m.subject, m.body, 'r/' + m.subreddit.name, m.created, time.time(), m.parent_id))
      else:
        self.c.execute('''INSERT INTO inbox(tid, subject, body, sender, sent, seen, parent_id) VALUES(?,?,?,?,?,?,?)''',
            (m.name, m.subject, m.body, m.author.name, m.created, time.time(), m.parent_id))
      return True
    except sqlite3.IntegrityError:
      return False

  def get_last_message(self):
    self.c.execute('''SELECT tid, sent FROM inbox ORDER BY seen DESC LIMIT 1''')
    last_message = self.c.fetchone()
    return last_message
