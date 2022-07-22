def get_sender(m):
  if m.subreddit:
    return add_r(m.subreddit.display_name)
  else:
    return m.author.name

def add_r(reddit):
    return 'r/' + reddit

def log(format, params=None, stderr=False,newline=True):
  prefix = time.strftime('%Y-%m-%d %H:%M:%S')
  logline = prefix + " " + (format if params is None else (format % params))
  if(newline):
    logline += "\n"

  # Some arcane nonsense to get Python2 to always output utf-8 even if the terminal encoding is not that
  out = sys.stderr if stderr else sys.stdout
  codecs.getwriter('utf-8')(out).write(logline)
