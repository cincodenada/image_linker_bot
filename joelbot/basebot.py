#!/usr/bin/python
# vim: sw=2 ts=2 sts=2 et :
import praw
import prawcore
import time
import yaml
import sys
import urlparse
import random

from .util import log

class BaseBot:
  max_retries = 50
  backoff = 2

  def __init__(self, config_file='config.yaml', useragent = 'default', skip_remote_config=False):
    #Load config and set up
    log("Logging in...")

    self.config_file = config_file
    self.load_config()

    self.start_time = time.time()

    self.useragent = useragent
    self.r = None

    if self.account_config['oauth']:
      while True:
        try:
          self.auth_oauth()
          break
        except praw.exceptions.APIException:
          self.backoff *= 2
          log("Error logging in! Trying again in {} seconds...".format(self.backoff), stderr=True)
        time.sleep(self.backoff)
    else:
      log("Error! Password login no longer supported!", stderr=True)
      sys.exit()

  def load_config(self):
    allconfig = yaml.load(open(self.config_file))
    self.config = allconfig['bot']
    self.account_config = allconfig['account']
    self.username = self.account_config['username']

  def reload_settings(self):
    log("Reloading config...")
    sys.stdout.flush()
    self.load_config()

  def auth_oauth(self):
    if self.get_refresh_token():
      self.r = praw.Reddit(
        user_agent = self.config['useragent'][self.useragent],
        refresh_token = self.refresh_token,
        **self.account_config['oauth']
      )
    else:
      self.r = praw.Reddit(
        user_agent = self.config['useragent'][self.useragent],
        **self.account_config['oauth']
      )
      rt = self.authorize_oauth()
      if rt:
        rtfile = open('refresh_token','w')
        rtfile.write(rt)
      else:
        raise prawcore.exceptions.OAuthException("Couldn't fetch refresh token!")

  def authorize_oauth(self):
    self.oauth_state = str(random.randint(0, 65000))
    auth_url = self.r.auth.url(
      self.config['oauth_scopes'],
      self.oauth_state,
      "permanent"
    )

    log('Go to the following URL, copy the URL that you are redirected to, then come back and paste it here:')
    log(auth_url)
    redirect_url = raw_input("Redirected URL: ")

    urlparts = urlparse.urlsplit(redirect_url)
    querydata = urlparse.parse_qs(urlparts.query)
    self.refresh_token = self.r.auth.authorize(querydata['code'])
    return self.refresh_token

  def get_refresh_token(self):
    # Check if we have a refresh token available
    try:
      rtfile = open('refresh_token','r')
      rt = rtfile.readline().rstrip()
      self.refresh_token = rt
      rtfile.close()
    except IOError:
      return None

    return self.refresh_token

  def id_string(self):
    return "{:s} ({:s}) {:f}".format(
      self.username,
      self.useragent or 'default',
      self.start_time
    )
