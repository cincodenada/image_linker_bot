#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import sqlite3
import time

class IgnoreList():
  def __init__(self, dbfilename, key="ignore"):
    self.key = key

    self.conn = sqlite3.connect(dbfilename)
    self.conn.row_factory = sqlite3.Row
    #Autocommit
    self.conn.isolation_level = None
    self.c = self.conn.cursor()

    self.c.execute('''CREATE TABLE IF NOT EXISTS {0}
        (username TEXT, request_id TEXT, {0}_date INTEGER)'''.format(self.key)
    self.c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS {0}_user ON {0}(username)'''.format(self.key))

  def ignore_sender(self, m):
    self.c.execute('''INSERT OR REPLACE INTO {0}(username, request_id, {0}_date) VALUES(?,?,?)'''.format(self.key),
        (m.author.name, m.name, time.time()))

  def unignore_sender(self, m):
    self.c.execute('''DELETE FROM {0} WHERE username=?'''.format(self.key), (m.author.name,))

  def is_ignored(self, name):
    self.c.execute('''SELECT username FROM {0} WHERE username=? LIMIT 1'''.format(self.key), (username,))
    user = self.c.fetchone();
    return (user is not None)
