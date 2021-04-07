from flask import redirect, session, flash, request
from functools import wraps

def login_required(f):
    """
    Decorate routes to require login.
    
    Documentation here:
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("id") is None:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def level_4(f):
    """
    Decorate routes to require level 4 previleges (Super Admin).
    IMPORTANT: Place this decorator in between the @app.route and @login_required
    Documentation here:
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") < 4:
            flash("Not enough previleges")
            return redirect("/?err=t")
        return f(*args, **kwargs)
    return decorated_function

def level_3(f):
    """
    Decorate routes to require level 3 previleges (Admin).
    IMPORTANT: Place this decorator in between the @app.route and @login_required
    Documentation here:
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") < 3:
            flash("Not enough previleges")
            return redirect("/?err=t")
        return f(*args, **kwargs)
    return decorated_function

def level_2(f):
    """
    Decorate routes to require level 2 previleges (Coach).
    IMPORTANT: Place this decorator in between the @app.route and @login_required
    Documentation here:
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") < 2:
            flash("Not enough previleges")
            return redirect("/?err=t")
        return f(*args, **kwargs)
    return decorated_function

def check_error():
    """Check if an error flag was passed in URL"""
    if request.args.get("err") == "t":
        return True
    else:
        return False

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS