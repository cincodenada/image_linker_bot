#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import time
import yaml
import json
import pickle
import collections
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
    self.log("Loading banlist...")
    sys.stdout.flush()
    bottiquette = self.r.get_wiki_page('Bottiquette', 'robots_txt_json')
    banlist = json.loads(bottiquette.content_md)
    btqban = (banlist['disallowed'] +\
        banlist['posts-only'] +\
        banlist['permission'])

    mybans = [x for x in list(open('blacklist.txt'))\
        if not (x.strip() == '' or x.startswith('#'))]
    
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

    return False

  def save_seen(self):
    self.comment_stream.save_state()

  def cleanup(self):
    subreddit_scores = {}

    # Comment deletion taken straight from autowikibot
    # No need to reinvent the wheel
    log("COMMENT SCORE CHECK CYCLE STARTED")
    user = self.r.get_redditor(self.config['account']['username'])
    total = 0
    upvoted = 0
    unvoted = 0
    downvoted = 0
    deleted = 0
    del_list = []
    total_score = 0
    score_list = []
            
    for c in user.get_comments(limit=None):
      
      if len(str(c.score)) == 4:
        spaces = ""
      if len(str(c.score)) == 3:
        spaces = " "
      if len(str(c.score)) == 2:
        spaces = "  "
      if len(str(c.score)) == 1:
        spaces = "   "
      
      #Keep track of our votes
      sub = c.subreddit.display_name
      if(sub not in subreddit_scores):
        subreddit_scores[sub] = 0
      subreddit_scores[sub] += c.score

      total = total + 1
      total_score += c.score
      score_list.append(c.score)

      if c.score < 1: # or sub.lower() in self.bans:
        del_list.append((sub.lower(), c.score, c.permalink))
        c.delete()
        print "\033[1;41m%s%s\033[1;m"%(spaces,c.score),
        deleted = deleted + 1
        downvoted = downvoted + 1
      elif c.score > 10:
        print "\033[1;32m%s%s\033[1;m"%(spaces,c.score),
        upvoted = upvoted + 1
      elif c.score > 1:
        print "\033[1;34m%s%s\033[1;m"%(spaces,c.score),
        upvoted = upvoted + 1
      elif c.score > 0:
        print "\033[1;30m%s%s\033[1;m"%(spaces,c.score),
        unvoted = unvoted + 1

      sys.stdout.flush()

    avg_score = float(total_score)/float(total) if total else 0
    print ("")
    log("COMMENT SCORE CHECK CYCLE COMPLETED")
    urate = round(upvoted / float(total) * 100)
    nrate = round(unvoted / float(total) * 100)
    drate = round(downvoted / float(total) * 100)
    warn("Upvoted:      %s\t%s\b\b %%"%(upvoted,urate))
    warn("Unvoted       %s\t%s\b\b %%"%(unvoted,nrate))
    warn("Downvoted:    %s\t%s\b\b %%"%(downvoted,drate))
    warn("Total:        %s"%total)
    warn("Avg Score:    %f"%avg_score)
    if have_quantile:
      quantspots = [0.25,0.5,0.75]
      score_list = sorted(score_list)
      quant = [quantile(score_list, q, issorted=True) for q in quantspots]
      warn("Quantiles:    %.1f-%.1f-%.1f"%tuple(quant))

    sys.stdout.flush()

    try:
      ss = open("subreddit_scores.%d.tsv" % (time.time()),"w")
      for sr, score in subreddit_scores.iteritems():
        ss.write("%s\t%d\n" % (sr, score)) 
      ss.close()
      dl = open("deleted_list.tsv","a")
      for cols in del_list:
        dl.write("\t".join(map(str, cols)) + "\n")
      dl.close()
    except Exception, e:
      warn(e)
      warn("Failed to write subreddit scores")

  def get_template(self):
    if('status_template' in self.config['bot']):
      template = self.config['bot']['status_template']
      if(template.find('\n') == -1):
        template = open(template, 'r').read()
      return template
    else:
      return '<html><head><title>JoelBot</title></head><body>No template found</body></html>'

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
