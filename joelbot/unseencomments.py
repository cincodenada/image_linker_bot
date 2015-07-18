#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import pickle
import praw
import time
import collections

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
