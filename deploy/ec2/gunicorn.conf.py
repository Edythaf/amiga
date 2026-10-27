"""One application worker owns the durable background queue; no preload/reloader."""
bind = '127.0.0.1:3000'
workers = 1
worker_class = 'gthread'
threads = 4
preload_app = False
reload = False
timeout = 180
graceful_timeout = 180
keepalive = 5
worker_tmp_dir = '/run/amiga'
accesslog = '-'
errorlog = '-'
# No query strings, cookies, authorization headers or request bodies in access logs.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(L)s'
forwarded_allow_ips = '127.0.0.1,::1'
