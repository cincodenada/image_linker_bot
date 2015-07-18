#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import time
import yaml
import json
import pickle
import collections
import sqlite3
from requests import exceptions as req_exceptions
from util import success, warn, log, fail, function_timeout
import sys
try:
  from quantile import quantile
  have_quantile = True
except:
  have_quantile = False

class JoelBot:
  def __init__(self, subreddit, config_file='config.yaml', useragent = None):
    #Load config and set up
    self.log("Logging in...")
    self.config = yaml.load(open(config_file))

    if useragent is None: 
      useragent = self.config['bot']['useragent']['default']
    else:
      useragent = self.config['bot']['useragent'][useragent]
    self.r = praw.Reddit(useragent)
    self.r.login(self.config['account']['username'],self.config['account']['password'])

    self.comment_stream = UnseenComments(self.r, subreddit, self.config['bot']['seen_len'])
    self.subreddit = subreddit

    self.load_settings()

    self.inbox = CommentStore(self.config['bot']['dbfile'])
    self.ignores = IgnoreList(self.config['bot']['dbfile'])

  def log(self, format, params=None, stderr=False,newline=True):
    prefix = time.strftime('%Y-%m-%d %H:%M:%S')
    logline = prefix + " " + (format if params is None else (format % params))
    if(newline and stderr):
      logline += "\n"

    if(stderr):
      sys.stderr.write(logline)
    else:
      print(logline)
    
  def load_settings(self):
    self.log("Reloading config...")
    sys.stdout.flush()
    self.config = yaml.load(open('config.yaml'))

    #Load banlist
    self.log("Loading banlists...")
    sys.stdout.flush()
    bottiquette = self.r.get_wiki_page('Bottiquette', 'robots_txt_json')
    banlist = json.loads(bottiquette.content_md)
    btqban = (banlist['disallowed'] +\
        banlist['posts-only'] +\
        banlist['permission'])

    try:
      mybans = self.r.get_wiki_page(self.config['bot']['subreddit'], 'blacklist')
      mybans = [line for line in mybans.content_md.split('\n')\
          if not (line.strip() == '' or line.startswith('#'))]
    except req_exceptions.HTTPError:
      self.log("Couldn't load bot-specific blacklist")
      mybans = []
    
    self.bans = [x.strip().lower() for x in (btqban + mybans)]
    self.log("Ignoring subreddits: %s",(', '.join(self.bans)))

  def should_ignore(self, comment):
    #Don't post in bot-banned subreddits
    subreddit = comment.subreddit.display_name.lower()
    if subreddit in self.bans:
      self.log("Skipping banned subreddit %s",(subreddit))
      return True

    #Don't reply to self, just in case...
    if comment.author.name == self.config['account']['username']:
      return True

    #Check user ignore list
    if self.ignores.check_ignored(comment.author.name):
      self.log("Ignoring user %s",(comment.author.name))
      return True

    return False

  def save_seen(self):
    self.comment_stream.save_state()

  def cleanup(self):
    sc = ScoreCheck(self)
    sc.run()
    sc.print_report()
    sc.save_report()


  def get_template(self):
    if('status_template' in self.config['bot']):
      template = self.config['bot']['status_template']
      if(template.find('\n') == -1):
        template = open(template, 'r').read()
      return template
    else:
      return '<html><head><title>JoelBot</title></head><body>No template found</body></html>'

  def refresh_comments(self):
    self.comment_stream.refresh_comments()

  def check_messages(self):
    last_message = self.inbox.get_last_message()
    last_tid = None if last_message is None else last_message['tid']
    for m in self.r.get_inbox(place_holder=last_tid):
      if(last_message is not None and m.created < last_message['sent']):
        self.log("Found old message, stopping!")
        return False

      if(self.inbox.add_message(m)):
        if(m.body in self.config['bot']['ignore_messages']):
          self.ignores.ignore_sender(m)
          if('ignore_reply' in self.config['bot']):
            self.reply_to(m, 'Ignore Request', self.config['bot']['ignore_reply'])
        elif(m.body in self.config['bot']['unignore_messages']):
          self.ignores.unignore_sender(m)
          if('unignore_reply' in self.config['bot']):
            self.reply_to(m, 'Unignore Request', self.config['bot']['unignore_reply'])
      else:
        self.log("Found duplicate message, stopping!")
        return False

  def reply_to(self, m, subject, reply):
    if(m.subreddit):
      # It's a comment, send a message
      self.r.send_message(m.author, subject, reply, raise_captcha_exception=True)
    else:
      # It's a pm, just reply
      m.reply(reply)


class ScoreCheck:
  def __init__(self, bot):
    self.conn = sqlite3.connect(bot.config['bot']['dbfile'])
    self.conn.row_factory = sqlite3.Row
    self.c = self.conn.cursor()

    self.colormap = {
      'none': 30,
      'up': 34,
      'up10': 32,
      'down': 41,
    }

    self.counts = {
      'total': 0,
      'upvoted': 0,
      'unvoted': 0,
      'downvoted': 0,
    }

    self.del_list = []
    self.score_map = {}
    self.subreddit_map = {}
    self.total_score = 0

    self.bot = bot

  def run(self):
    # Comment deletion taken straight from autowikibot
    # No need to reinvent the wheel
    log("COMMENT SCORE CHECK CYCLE STARTED")
    user = self.bot.r.get_redditor(self.bot.config['account']['username'])
            
    for c in user.get_comments(limit=None):
      
      # Sum votes for each subreddit
      self.subreddit_map[c.id] = c.subreddit.display_name

      self.counts['total'] += 1
      self.total_score += c.score
      self.score_map[c.id] = c.score

      colorname = 'none'
      if c.score < 1: # or sub.lower() in self.bot.bans:
        self.del_list.append((sub.lower(), c.score, c.id))
        c.delete()
        self.counts['downvoted'] += 1
        colornamesc = 'down' 
      elif c.score > 10:
        colorname = 'up10'
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
    urate = round(self.counts['upvoted'] / float(self.counts['total']) * 100)
    nrate = round(self.counts['unvoted'] / float(self.counts['total']) * 100)
    drate = round(self.counts['downvoted'] / float(self.counts['total']) * 100)
    warn("Upvoted:      %s\t%s\b\b %%"%(self.counts['upvoted'],urate))
    warn("Unvoted       %s\t%s\b\b %%"%(self.counts['unvoted'],nrate))
    warn("Downvoted:    %s\t%s\b\b %%"%(self.counts['downvoted'],drate))
    warn("Total:        %s"%self.counts['total'])
    warn("Avg Score:    %f"%self.avg_score)
    if have_quantile:
      quantspots = [0.25,0.5,0.75]
      score_list = sorted(self.score_map.values())
      quant = [quantile(score_list, q, issorted=True) for q in quantspots]
      warn("Quantiles:    %.1f-%.1f-%.1f"%tuple(quant))

    sys.stdout.flush()

  def save_report(self):
    try:
      ts = time.time()

      # Comment scores
      self.c.execute('''CREATE TABLE IF NOT EXISTS comment_scores
          (cid TEXT, subreddit TEXT, score INTEGER, ts INTEGER)''')
      self.c.execute('''CREATE INDEX IF NOT EXISTS cscores_time ON comment_scores(ts)''')

      for cid, score in self.score_map.iteritems():
        self.c.execute('''INSERT INTO comment_scores VALUES(?,?,?,?)''',
            (cid, self.subreddit_map[cid], score, ts))
      self.conn.commit()

      # Deleted comments
      self.c.execute('''CREATE TABLE IF NOT EXISTS deleted_comments
          (cid TEXT, subreddit TEXT, score INTEGER, ts INTEGER)''')
      self.c.execute('''CREATE INDEX IF NOT EXISTS cscores_time ON comment_scores(ts)''')

      for cols in self.del_list:
        cols.append(ts)
        self.c.execute('''INSERT INTO deleted_comments VALUES(?,?,?,?)''', cols)
      self.conn.commit()

    except Exception, e:
      warn(e)
      warn("Failed to write subreddit scores")


class UnseenComments:
  def __init__(self, r, subreddit, maxlen=1000, state_file='seen.pickle'):
    self.r = r
    self.subreddit = subreddit
    self.state_file = state_file
    self.refresh_comments()

    #Load already-checked queue
    try:
      self.already_seen = pickle.load(open(state_file))
    except Exception:
      self.already_seen = collections.deque(maxlen=maxlen)

  def __iter__(self):
    return self

  def refresh_comments(self):
    self.comment_stream = praw.helpers.comment_stream(self.r, self.subreddit, limit=None, verbosity=0)

  def next(self):
    next_comment = self.comment_stream.next()
    #Deal with reaching the end of comment streams?
    if next_comment is None:
      self.refresh_comments()
      next_comment = self.comment_stream.next()
      while(next_comment is None):
        time.sleep(5)
        next_comment = self.comment_stream.next()

    if next_comment.id in self.already_seen:
      print "Already saw comment %s, skipping..." % (next_comment.id)
      return self.next()

    self.already_seen.append(next_comment.id)
    return next_comment;

  def save_state(self):
    return pickle.dump(self.already_seen,open(self.state_file,'w'))

class CommentStore():
  def __init__(self, dbfilename):
    self.conn = sqlite3.connect(dbfilename)
    self.conn.row_factory = sqlite3.Row
    self.conn.isolation_level = None
    self.c = self.conn.cursor()

    self.c.execute('''CREATE TABLE IF NOT EXISTS inbox
        (tid TEXT, subject TEXT, body TEXT, sender TEXT, sent INTEGER, seen INTEGER)''')
    self.c.execute('''CREATE INDEX IF NOT EXISTS inbox_seen ON inbox(seen)''')
    self.c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS inbox_id ON inbox(tid)''')

  def add_message(self, m):
    try:
      self.c.execute('''INSERT INTO inbox VALUES(?,?,?,?,?,?)''', 
          (m.name, m.subject, m.body, m.author.name, m.created, time.time()))
      return True
    except sqlite3.IntegrityError:
      return False

  def get_last_message(self):
    self.c.execute('''SELECT tid, sent FROM inbox ORDER BY seen DESC LIMIT 1''')
    last_message = self.c.fetchone()
    return last_message

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

