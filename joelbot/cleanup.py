#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import sqlite3
import time
import sys

from .basebot import BaseBot
from .util import success, warn, log, fail, function_timeout

try:
  from quantile import quantile
  have_quantile = True
except:
  have_quantile = False

class CleanupBot(BaseBot):
  def __init__(self, **kwargs):
    BaseBot.__init__(self, useragent='cleanup', **kwargs)

    self.conn = sqlite3.connect(self.config['dbfile'])
    self.conn.row_factory = sqlite3.Row
    # Leave autocommit off
    self.c = self.conn.cursor()

    self.colormap = {
      'none': 30,
      'up': 34,
      'up10': 32,
      'down': 41,
    }

    self.counts = {
      'total': 0,
      'up10': 0,
      'upvoted': 0,
      'unvoted': 0,
      'downvoted': 0,
    }

    self.del_list = []
    self.score_map = {}
    self.subreddit_map = {}
    self.total_score = 0

  def run(self, delete_negative = True):
    # Comment deletion taken straight from autowikibot
    # No need to reinvent the wheel
    log("COMMENT SCORE CHECK CYCLE STARTED")
    user = self.r.redditor(self.username)
            
    for c in user.comments.new(limit=None):
      
      # Sum votes for each subreddit
      sub = c.subreddit.display_name
      self.subreddit_map[c.id] = sub

      self.counts['total'] += 1
      self.total_score += c.score
      self.score_map[c.id] = c.score

      colorname = 'none'
      if c.score < 1:
        if(delete_negative):
          self.del_list.append((sub.lower(), c.score, c.id))
          c.delete()
        self.counts['downvoted'] += 1
        colornamesc = 'down' 
      elif c.score > 10:
        colorname = 'up10'
        self.counts['up10'] += 1
        self.counts['upvoted'] += 1
      elif c.score > 1:
        colorname = 'up'
        self.counts['upvoted'] += 1
      elif c.score > 0:
        colorname = 'none'
        self.counts['unvoted'] += 1

      # Print the list entry
      print self.color_num(c.score, colorname),
      sys.stdout.flush()

    self.avg_score = float(self.total_score)/float(self.counts['total']) if self.counts['total'] else 0

  def color(self, instr, color):
    if not color.isdigit():
      color = self.colormap[color]

    return "\033[1;{0:d}m{1:s}\033[1;m".format(color, instr)

  def color_num(self, num, color):
    return self.color("{: 4d}".format(num), color)

  def print_report(self):
    print ("")
    log("COMMENT SCORE CHECK CYCLE COMPLETED")
    u10rate = round(self.counts['up10'] / float(self.counts['total']) * 100)
    urate = round(self.counts['upvoted'] / float(self.counts['total']) * 100)
    nrate = round(self.counts['unvoted'] / float(self.counts['total']) * 100)
    drate = round(self.counts['downvoted'] / float(self.counts['total']) * 100)
    warn("Score > 10:   %s\t%s\b\b %%",(self.counts['up10'],u10rate))
    warn("Upvoted:      %s\t%s\b\b %%",(self.counts['upvoted'],urate))
    warn("Unvoted       %s\t%s\b\b %%",(self.counts['unvoted'],nrate))
    warn("Downvoted:    %s\t%s\b\b %%",(self.counts['downvoted'],drate))
    warn("Total:        %s",self.counts['total'])
    warn("Avg Score:    %f",self.avg_score)
    if have_quantile:
      quantspots = [0.25,0.5,0.75]
      score_list = sorted(self.score_map.values())
      quant = [quantile(score_list, q, issorted=True) for q in quantspots]
      warn("Quantiles:    %.1f-%.1f-%.1f",tuple(quant))

    sys.stdout.flush()

  def save_report(self):
    try:
      ts = time.time() 

      # Comment scores
      self.c.execute('''CREATE TABLE IF NOT EXISTS comment_scores
          (cid TEXT, subreddit TEXT, score INTEGER, ts INTEGER)''')
      self.c.execute('''CREATE INDEX IF NOT EXISTS cscores_time ON comment_scores(ts)''')

      for cid, score in self.score_map.iteritems():
        self.c.execute('''INSERT INTO comment_scores(cid, subreddit, score, ts) VALUES(?,?,?,?)''',
            (cid, self.subreddit_map[cid], score, ts))
      self.conn.commit()

      # Deleted comments
      self.c.execute('''CREATE TABLE IF NOT EXISTS deleted_comments
          (cid TEXT, subreddit TEXT, score INTEGER, ts INTEGER)''')
      self.c.execute('''CREATE INDEX IF NOT EXISTS cscores_time ON comment_scores(ts)''')

      for cols in self.del_list:
        # I'm sure this could be done better
        curcols = list(cols)
        curcols.append(ts)
        self.c.execute('''INSERT INTO deleted_comments(cid, subreddit, score, ts) VALUES(?,?,?,?)''', curcols)
      self.conn.commit()

    except Exception, e:
      warn(e)
      warn("Failed to write subreddit scores")
