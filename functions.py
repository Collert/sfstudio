from flask import redirect, session, flash
from functools import wraps

def login_required(f):
    """
    Decorate routes to require login.
    
    Documentation here:
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("school_id") is None:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Decorate routes to require admin previleges.
    Documentation here:
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Not enough previleges")
            return redirect("/?err=t")
        return f(*args, **kwargs)
    return decorated_function