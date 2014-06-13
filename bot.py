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
  reply = "\n".join(lines) + "\n\n" + config['comments']['footer']
  return reply

parser = argparse.ArgumentParser(description="Links text such as themoreyouknow.gif to actual images")

#Load config and set up
print "Logging in..."
config = yaml.load(open('config.yaml'))
r = praw.Reddit('Image Text Linker by /u/cincodenada v 0.1')
r.login(config['account']['username'],config['account']['password'])

#Load banlist
print "Loading banlist..."
bottiquette = r.get_wiki_page('Bottiquette', 'robots_txt_json')
banlist = json.loads(bottiquette.content_md)
bans = banlist['disallowed'] +\
  banlist['posts-only'] +\
  banlist['permission']

#Load image map
maybeimage = re.compile(r'(?:^|\s)(\w+)\.(jpeg|png|gif|jpg|bmp)\b',re.IGNORECASE)
imagemap = load_imagelist(config)
print "Starting up with image map:"
pprint(imagemap)

numchecked = 0
try:
  while True:
    for comment in praw.helpers.comment_stream(r, 'all', limit=None, verbosity=0):
      if hasattr(comment,'body'):
        numchecked += 1
        sys.stderr.write("\rChecked %d comments..." % (numchecked))

        commentlinks = collections.OrderedDict()
        foundkeys = []
        matches = maybeimage.findall(comment.body)
        for match in matches:
          #Don't post in bot-banned subreddits
          subreddit = comment.submission.subreddit.display_name
          if subreddit in bans:
            print "Skipping banned subreddit %s" % (comment.submission.subreddit.display_name)
            break

          #Add the match to the list if it's not a dup
          (key, ext) = match
          if key not in foundkeys:
            if key in imagemap:
              urls = imagemap[key]
              #Follow aliases
              if not isinstance(urls, list):
                key = urls
                if key in foundkeys: continue
                urls = imagemap[key]

              foundkeys.append(key)
              commentlinks["%s.%s" % (key,ext)] = random.choice(urls)
            else:
              print u"\nPossible new image for %s - %s" % (comment.permalink, match)
        
        if len(commentlinks):
          replytext = form_reply(commentlinks)
          print "Commenting on %s" % (comment.permalink)
          comment.reply(replytext)
          
except KeyboardInterrupt:
  print "Shutting down..."
