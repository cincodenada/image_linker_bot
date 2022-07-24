from .basebot import BaseBot
from .util import log, get_sender
from ignorelist import IgnoreList
from commentstore import CommentStore

class InboxBot(BaseBot):
  def __init__(self, **kwargs):
    BaseBot.__init__(self, **kwargs)

    self.inbox = CommentStore(self.config['dbfile'])
    self.ignores = IgnoreList(self.config['dbfile'], 'ignore')
    self.bans = IgnoreList(self.config['dbfile'], 'ban')

  def matches_action(self, message, action):
    return any([match in message for match in self.config['{}_messages'.format(action)]])

  def check_messages(self):
    last_tid = None
    last_message = self.inbox.get_last_message()
    if last_message is not None:
      _, last_tid = last_message['tid'].split('_', 1)
    # TODO: Make continuous/stream-based?
    for m in self.r.inbox.messages(params={'after': last_tid}):
      if(last_message is not None and m.created < last_message['sent']):
        log("Found old message, stopping!")
        return False

      if(self.inbox.add_message(m)):
        action = self.get_command(m.body)
        if action:
          self.do_command(action, get_sender(m), m.name)
          config = self.config['actions'][action]
          if config['reply']:
            self.reply_to(m, config.get('subject'), config['reply'])
      else:
        log("Found duplicate message, stopping!")
        return False

  def get_command(self, message):
    for action in self.config['actions'].items():
      if(self.matches_action(message, action)):
        return action
    return None

  def do_command(self, action, target, ref_id=None, reason=None):
    if action == 'ignore':
      log("Ignoring {:s}...".format(target))
      self.ignores.ignore_sender(target, ref_id, reason or "message")

    elif action == 'unignore':
      log("Unignoring {:s}...".format(target))
      self.ignores.unignore_sender(target)

    elif action == 'ban':
      log("Recording ban from {:s}...".format(target))
      self.bans.ignore_sender(target, ref_id, reason or "ban")

    elif action == 'softban':
      log("Recording soft ban from {:s}...".format(target))
      self.bans.ignore_sender(target, ref_id, reason or "softban")

  def reply_to(self, m, subject, reply):
    if(m.subreddit):
      # It's a comment, send a message
      self.r.send_message(m.author, subject, reply, raise_captcha_exception=True)
    else:
      # It's a pm, just reply
      m.reply(reply)
