class RedisError(Exception):pass
PUSHED=[]
class Redis:
 @classmethod
 def from_url(cls,url):return cls()
 def rpush(self,*args):PUSHED.append(args);return len(PUSHED)
 def blpop(self,*a,**k):return None
 def ping(self):return True
