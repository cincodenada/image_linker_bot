#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import sqlite3

class IgnoreList():
  def __init__(self, dbfilename):
    self.conn = sqlite3.connect(dbfilename)
    self.conn.row_factory = sqlite3.Row
    #Autocommit
    self.conn.isolation_level = None
    self.c = self.conn.cursor()

    self.c.execute('''CREATE TABLE IF NOT EXISTS ignore
        (username TEXT, request_id TEXT, ignore_date INTEGER)''')
    self.c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS ignore_user ON ignore(username)''')

  def ignore_sender(self, m):
    self.c.execute('''INSERT OR REPLACE INTO ignore VALUES(?,?,?)''', 
        (m.author.name, m.name, time.time()))

  def unignore_sender(self, m):
    self.c.execute('''DELETE FROM ignore WHERE username=?''', (m.author.name,))

  def check_ignored(self, username):
    self.c.execute('''SELECT username FROM ignore WHERE username=? LIMIT 1''', (username,))
    user = self.c.fetchone();
    return (user is not None)
