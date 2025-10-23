import os, time, jwt
from fastapi import HTTPException, Depends, Header

JWT_SECRET = os.getenv('JWT_SECRET','devsecret')
JWT_ISS = 'gpu-reseller'

def make_jwt(user_id:str, org_id:str, minutes:int=60*24):
    now = int(time.time())
    payload = { 'sub': user_id, 'org': org_id, 'iss': JWT_ISS, 'iat': now, 'exp': now+minutes*60 }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def require_jwt(authorization: str = Header(None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401,'missing token')
    token = authorization.split(' ',1)[1]
    try:
      return jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer=JWT_ISS)
    except Exception:
      raise HTTPException(401,'bad token')
