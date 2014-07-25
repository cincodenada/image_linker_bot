#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import time
import praw
import re 
import sys
import argparse
import yaml
import json
from pprint import pprint
import random
import collections
import pickle
import signal
from util import success, warn, log, fail
import shutil

def load_imagelist(config):
  matchlist = {}
  for key, urls in config['images'].iteritems():
    if(not isinstance(urls, list)):
      urls = [urls]
    matchlist[key] = urls

  for key, aliases in config['aliases'].iteritems():
    if(not isinstance(aliases, list)):
      aliases = [aliases]

    for alias in aliases:
      matchlist[alias] = key

  return matchlist

def print_imagelist(config, format = 'markdown'):
  headers = {
    'markdown': "|Triggers|Responses|\n|:-|:-|\n"
  }
  imagelist = headers[format];
  for key, urls in config['images'].iteritems():
    keylist = [key]
    if(not isinstance(urls, list)):
      urls = [urls]
    if(key in config['aliases']):
      aliases = config['aliases'][key]
      if(not isinstance(aliases, list)):
        aliases = [aliases]
      keylist += aliases
    
    if(format == 'markdown'):
       imagelist += "|%s|%s|\n" % (', '.join(keylist), ' '.join(['[%d](%s)' % (i+1,url) for i, url in enumerate(urls)]))

  return imagelist

def form_reply(link_list):
  lines = ["[%s](%s)  " % keyval for keyval in link_list.iteritems()]
  reply = "\n".join(lines) + "\n\n" + config['bot']['footer']
  return reply

def cleanup():
  global last_cleaned

  if(last_cleaned and last_cleaned > (time.time() - config['bot']['cleanup_time'])):
    return

  subreddit_scores = {}
  last_cleaned = time.time()

  # Comment deletion taken straight from autowikibot
  # No need to reinvent the wheel
  log("COMMENT SCORE CHECK CYCLE STARTED")
  user = r.get_redditor(config['account']['username'])
  total = 0
  upvoted = 0
  unvoted = 0
  downvoted = 0
  deleted = 0
  del_list = []
          
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

    if c.score < 1: # or sub.lower() in bans:
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

  print ("")
  log("COMMENT SCORE CHECK CYCLE COMPLETED")
  urate = round(upvoted / float(total) * 100)
  nrate = round(unvoted / float(total) * 100)
  drate = round(downvoted / float(total) * 100)
  warn("Upvoted:      %s\t%s\b\b %%"%(upvoted,urate))
  warn("Unvoted       %s\t%s\b\b %%"%(unvoted,nrate))
  warn("Downvoted:    %s\t%s\b\b %%"%(downvoted,drate))
  warn("Total:        %s"%total)

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

def signal_handler(signum, frame):
  if(signum == signal.SIGHUP):
      load_settings()


def load_settings():
  global bans
  global config
  global imagemap
  global r

  print "Reloading config..."
  sys.stdout.flush()
  config = yaml.load(open('config.yaml'))

  #Load banlist
  print "Loading banlist..."
  sys.stdout.flush()
  bottiquette = r.get_wiki_page('Bottiquette', 'robots_txt_json')
  banlist = json.loads(bottiquette.content_md)
  btqban = (banlist['disallowed'] +\
      banlist['posts-only'] +\
      banlist['permission'])

  mybans = [x for x in list(open('blacklist.txt'))\
      if not (x.strip() == '' or x.startswith('#'))]
  
  bans = [x.strip().lower() for x in (btqban + mybans)]
  print "Ignoring subreddits: %s" % (', '.join(bans))

  #Load image map
  imageconf = yaml.load(open('imagelist.yaml'))
  imagemap = load_imagelist(imageconf)

  markdown = print_imagelist(imageconf)

  shutil.copy('imagelist.md','imagelist.previous.md')
  mdf = open('imagelist.md','w')
  mdf.write(markdown)
  mdf.close()

  print "Loaded image map:"
  pprint(imagemap)
  sys.stdout.flush()

parser = argparse.ArgumentParser(description="Links text such as themoreyouknow.gif to actual images")

#Load config and set up
print "Logging in..."
config = yaml.load(open('config.yaml'))
r = praw.Reddit('Image Text Linker by /u/cincodenada v0.1 at /r/image_linker_bot')
r.login(config['account']['username'],config['account']['password'])

load_settings()
signal.signal(signal.SIGHUP,signal_handler)

ext_list = '|'.join(config['bot']['extensions'])
maybeimage = re.compile(r'(^|\s|\^)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

#Load already-checked queue
try:
  already_seen = pickle.load(open('seen.pickle'))
except Exception:
  already_seen = collections.deque(maxlen=config['bot']['seen_len'])

global last_cleaned
last_cleaned = 0

numchecked = 0
while True:
  try:
    for comment in praw.helpers.comment_stream(r, 'all', limit=None, verbosity=0):
      cleanup()

      if comment.id in already_seen:
        print "Already saw comment %s, skipping..." % (comment.id)
        continue

      already_seen.append(comment.id)

      if hasattr(comment,'body'):
        numchecked += 1
        sys.stderr.write("\rChecked %d comments..." % (numchecked))

        commentlinks = collections.OrderedDict()
        foundkeys = []
        matches = maybeimage.findall(comment.body)
        if len(matches):
          #Don't post in bot-banned subreddits
          subreddit = comment.subreddit.display_name.lower()
          if subreddit in bans:
            print "Skipping banned subreddit %s" % (subreddit)
            continue

          #Don't reply to self, just in case...
          if comment.author.name == config['account']['username']:
            continue

          for match in matches:
            #Add the match to the list if it's not a dup
            (prefix, key, ext) = match
            searchkey = key.lower()
            if searchkey not in foundkeys:
              if searchkey in imagemap:
                urls = imagemap[searchkey]
                #Follow aliases
                if not isinstance(urls, list):
                  searchkey = urls.lower()
                  if searchkey in foundkeys: continue
                  urls = imagemap[searchkey]

                foundkeys.append(searchkey)
                linktext = "%s.%s" % (key,ext)
                if(prefix == '^'):
                  linktext = '^' + linktext
                commentlinks[linktext] = random.choice(urls)
              else:
                print u"\nPossible new image for %s\n%s" % (comment.permalink, ' '.join(match))
          
          if len(commentlinks):
            if(not comment.is_root):
              parent = r.get_info(thing_id=comment.parent_id)
              subreddit = comment.subreddit.display_name.lower()
              if(parent.author.name == config['account']['username'] and subreddit != config['account']):
                print "Sending warning to %s for reply-reply..." % (comment.author)
                r.send_message(comment.author,'I\'m glad you like me, but...',config['bot']['toomuch'],raise_captcha_exception=True)
                continue

            replytext = form_reply(commentlinks)
            try:
              print "Commenting on %s (%s)" % (comment.permalink, ', '.join(commentlinks.keys()))
              comment.reply(replytext)
            except praw.errors.RateLimitExceeded, e:
              print "Rate limit exceeded, sleeping %d seconds and trying again..." % (e.sleep_time)
              time.sleep(e.sleep_time)
              print "Re-commenting on %s" % (comment.permalink)
              comment.reply(replytext)

      sys.stdout.flush()
            
  except KeyboardInterrupt:
    print "Shutting down after scanning %d comments..." % (numchecked)
    pickle.dump(already_seen,open('seen.pickle','w'))
    sys.exit("Keyboard interrupt, shutting down...")
  except Exception, e:
    pprint(e)
