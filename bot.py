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

def form_reply(link_list):
  lines = ["[%s](%s)  " % keyval for keyval in link_list.iteritems()]
  reply = "\n".join(lines) + "\n\n" + config['bot']['footer']
  return reply

def signal_handler(signum, frame):
  if(signum == signal.SIGHUP):
      load_settings()


def load_settings():
  global bans
  global config
  global imagemap

  print "Reloading config..."
  config = yaml.load(open('config.yaml'))

  #Load banlist
  print "Loading banlist..."
  bottiquette = r.get_wiki_page('Bottiquette', 'robots_txt_json')
  banlist = json.loads(bottiquette.content_md)
  bans = banlist['disallowed'] +\
    banlist['posts-only'] +\
    banlist['permission']

  #Load image map
  imageconf = yaml.load(open('imagelist.yaml'))
  imagemap = load_imagelist(imageconf)
  print "Loaded image map:"
  pprint(imagemap)


parser = argparse.ArgumentParser(description="Links text such as themoreyouknow.gif to actual images")

#Load config and set up
print "Logging in..."
config = yaml.load(open('config.yaml'))
r = praw.Reddit('Image Text Linker by /u/cincodenada v0.1 at /r/image_linker_bot')
r.login(config['account']['username'],config['account']['password'])

load_settings()
signal.signal(signal.SIGHUP,signal_handler)

maybeimage = re.compile(r'(?:^|\s)(\w+)\.(jpeg|png|gif|jpg|bmp)\b',re.IGNORECASE)

#Load already-checked queue
try:
  already_seen = pickle.load(open('seen.pickle'))
except Exception:
  already_seen = collections.deque(maxlen=config['bot']['seen_len'])

numchecked = 0
try:
  while True:
    for comment in praw.helpers.comment_stream(r, 'all', limit=None, verbosity=0):
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
          subreddit = comment.submission.subreddit.display_name
          if subreddit in bans:
            print "Skipping banned subreddit %s" % (comment.submission.subreddit.display_name)
            continue

          #Don't reply to self, just in case...
          if comment.author == config['account']['username']:
            continue

          for match in matches:
            #Add the match to the list if it's not a dup
            (key, ext) = match
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
                commentlinks["%s.%s" % (key,ext)] = random.choice(urls)
              else:
                print u"\nPossible new image for %s\n%s" % (comment.permalink, ' '.join(match))
          
          if len(commentlinks):
            replytext = form_reply(commentlinks)
            try:
              print "Commenting on %s" % (comment.permalink)
              comment.reply(replytext)
            except praw.errors.RateLimitExceeded, e:
              print "Rate limit exceeded, sleeping %d seconds and trying again..." % (e.sleep_time)
              time.sleep(e.sleep_time)
              print "Re-commenting on %s" % (comment.permalink)
              comment.reply(replytext)

      sys.stdout.flush()
            
except (KeyboardInterrupt, Exception), e:
  pprint(e)
  print "Shutting down..."
  pickle.dump(already_seen,open('seen.pickle','w'))
