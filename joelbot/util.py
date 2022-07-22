def get_sender(m):
  if m.subreddit:
    return add_r(m.subreddit.display_name)
  else:
    return m.author.name

def add_r(reddit):
    return 'r/' + reddit
