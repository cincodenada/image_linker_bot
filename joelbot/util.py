### Logging borrowed from autowikibot @ https://github.com/acini/autowikibot-py
### Which was in turn borrowed from Zack Maril @ https://github.com/zmaril
import re, time, sys, codecs

def formatted(format, params=None):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    return "["+now+"] " + (format if params is None else (format % params))

def log(format, params=None, stderr=False,newline=True):
  logline = formatted(format, params)
  if(newline):
    logline += "\n"

  # Some arcane nonsense to get Python2 to always output utf-8 even if the terminal encoding is not that
  out = sys.stderr if stderr else sys.stdout
  codecs.getwriter('utf-8')(out).write(logline)

def fail(msg, **kwargs):
    log('\033[91m'+msg+'\033[0m', **kwargs)

def warn(msg, **kwargs):
    log('\033[93m'+msg+'\033[0m', **kwargs)

def success(msg, **kwargs):
    log('\033[92m'+msg+'\033[0m', **kwargs)

def special(msg, **kwargs):
    log('\033[95m'+msg+'\033[0m', **kwargs)

def bluelog(msg, **kwargs):
    log('\033[94m'+msg+'\033[0m', **kwargs)

#Decorator borrowed from http://compgroups.net/comp.lang.python/max-time-wait-for-a-function/182496
def function_timeout(seconds):
    """Function decorator to raise a timeout on a function call"""
    import signal
    class FunctionTimeOut(Exception):
        pass

    def decorate(f):
        def timeout(signum, frame):
            raise FunctionTimeOut()

        def funct(*args, **kwargs):
            old = signal.signal(signal.SIGALRM, timeout)
            signal.alarm(seconds)

            try:
                result = f(*args, **kwargs)
            finally:
                signal.signal(signal.SIGALRM, old)
            signal.alarm(0)
            return result

        return funct

    return decorate

# Custom stuff
def get_sender(m):
  if m.subreddit:
    return add_r(m.subreddit.display_name)
  else:
    return m.author.name

def add_r(reddit):
    return 'r/' + reddit
