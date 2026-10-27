"""Signed access JWTs. Database revocation keeps logout immediate."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import secrets
import jwt


def signing_key(config):
    return sha256((str(config['SECRET_KEY']) + ':amiga:access:v1').encode()).digest()


def issue_token(user_id, config):
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(hours=config['SESSION_HOURS'])
    token = jwt.encode({'sub': user_id, 'jti': secrets.token_urlsafe(32), 'iat': issued,
                        'exp': expires, 'iss': 'amiga', 'aud': 'amiga-workspace'},
                       signing_key(config), algorithm='HS256')
    return token, expires.isoformat(timespec='seconds').replace('+00:00', 'Z')


def verify_token(token, config):
    return jwt.decode(token, signing_key(config), algorithms=['HS256'], issuer='amiga',
                      audience='amiga-workspace', options={'require': ['sub', 'jti', 'iat', 'exp', 'iss', 'aud']})
