import time
import praw
import re 
import sys
import argparse

r = praw.Reddit('Image Text Linker by /u/cincodenada v 0.1')
#r.login()

maybeimage = re.compile(r'(?:^|\s)(\w+)\.(?:jpeg|png|gif|jpg|bmp)\b',re.IGNORECASE)
imagemap = {
  'thatsthejoke': 'http://i.imgur.com/Z5pWhBi.jpg',
  'themoreyouknow': 'tmyk',
  'tmyk': 'tmyk',
}

numchecked = 0
while True:
  for comment in praw.helpers.comment_stream(r, 'all', limit=None, verbosity=0):
    if(hasattr(comment,'body')):
      numchecked += 1
      sys.stdout.write("\rChecked %d comments..." % (numchecked))
      matches = maybeimage.findall(comment.body)
      for match in matches:
        if match in imagemap:
          print u"\nI want to comment on %s - %s" % (comment.permalink, imagemap[match])
        else:
          print u"\nPossible new image for %s - %s" % (comment.permalink, match)
