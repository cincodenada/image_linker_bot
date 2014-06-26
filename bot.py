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
maybeimage = re.compile(r'(?:^|\s)(\w+)\.(%s)\b' % (ext_list),re.IGNORECASE)

#Load already-checked queue
try:
  already_seen = pickle.load(open('seen.pickle'))
except Exception:
  already_seen = collections.deque(maxlen=config['bot']['seen_len'])

numchecked = 0
while True:
  try:
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
          subreddit = comment.submission.subreddit.display_name.lower()
          if subreddit in bans:
            print "Skipping banned subreddit %s" % (subreddit)
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
                matchurl = random.choice(urls)
                urlext = re.search(r'\.(\w+)$',matchurl)
                useext = urlext.group(1) if urlext else ext
                commentlinks["%s.%s" % (key,useext)] = matchurl
              else:
                print u"\nPossible new image for %s\n%s" % (comment.permalink, ' '.join(match))
          
          if len(commentlinks):
            if(not comment.is_root):
              parent = r.get_info(thing_id=comment.parent_id)
              subreddit = comment.submission.subreddit.display_name.lower()
              if(parent.author == config['account'] and subreddit != config['account']):
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
