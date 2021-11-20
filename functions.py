from datetime import datetime, time
from operator import or_
from flask import redirect, session, flash, request
from functools import wraps

from flask.helpers import url_for
from sqlalchemy.orm import relation
from models import *

def create_event(title, start, end, capacity, location, coach, private):
    """Create event and submit to database"""
    event = Class(title=title, start=start, end=end, capacity=capacity, location=location, coach=coach, free=capacity, private=private)
    db.session.add(event)
    db.session.commit()
    return event

def create_event_request(creator, title, start, end, location, coach):
    """Request a 1:1 event with a specialist"""
    event = EventRequest(creator=creator, title=title, start=start, end=end, location=location, coach=coach)
    db.session.add(event)
    db.session.commit()
    return event

def check_booking_requests(user_id):
    """Check any notifications for booking requests for 1:1s"""
    requests = db.session.query(EventRequest).filter(EventRequest.coach == user_id, EventRequest.accepted == None).all()
    return requests

def check_user_notifications(user_id):
    """Check notifications for any accepted or rejected booking requests"""
    requests = db.session.query(Notification).filter(Notification.owner == user_id).all()
    return requests

def clear_request(reqest_id):
    """Delete EventRequest from database"""
    request = db.session.query(EventRequest).get(reqest_id)
    if request.accepted != None: # If request has been responded to
        if not request:
            return 1
        db.session.delete(request)
        db.session.commit()
        return

def make_notification(user_id, message, category):
    """Create a notification for specified user"""
    notification = Notification(owner=user_id, message=message, category=category, time=datetime.now())
    db.session.add(notification)
    db.session.commit()

def delete_notification(notification_id):
    """Delete a notification from database"""
    notification = db.session.query(Notification).get(notification_id)
    db.session.delete(notification)
    db.session.commit()

def remove_ticket(owner_id, addon_id):
    """Look up a pass and remove 1 ticket from it. If pass doesn't have enough tickets, return an error message"""
    passes = db.session.query(Pass).filter(Pass.owner == owner_id, Pass.addons == addon_id).all()
    if not passes:
        flash("У вас немає підходящого абонемента")
        return redirect(url_for("profile_own"), err="t")
    for pas in passes:
        if pas.tickets > 0:
            pas.tickets -= 1
            db.session.commit()
    flash("Ваші абонементи пусті. Зверніться до адміністрації щоб придбати новий")
    return redirect(url_for("profile_own"), err="t")

def register_for_event(user_id, event_id):
    """Register given user for given event"""
    relation = Relationship(participant=user_id, classs=event_id)
    db.session.add(relation)
    db.session.commit()

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
    IMPORTANT: Place this decorator in after @login_required
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
    IMPORTANT: Place this decorator in after @login_required
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
    IMPORTANT: Place this decorator in after @login_required
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