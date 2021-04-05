from http.client import error
from logging import log
from re import U
from tempfile import mkdtemp
import os
from threading import Event

from sqlalchemy import create_engine, or_, and_, sql
from sqlalchemy.orm import query, relation, relationship, scoped_session, sessionmaker
from flask import Flask, flash, redirect, render_template, request, session, jsonify, make_response, send_from_directory, url_for
from flask_session import Session
from sqlalchemy.sql.expression import true
from sqlalchemy.sql.functions import user
from werkzeug.utils import secure_filename
from google.oauth2 import id_token
from google.auth.transport import requests

from functions import *
from models import *

##########
# Config #
##########

#App config
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")

Session(app)
db.init_app(app)

#Constants
G_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")

##########
# Routes #
##########

@app.route("/")
@login_required
def home():
    """Display homepage"""
    events = db.session.query(Relationship, Class).join(Class, Class.id == Relationship.classs).filter(Relationship.participant == 1).all()
    return render_template("home.html", error=check_error(), user=session, events=events)

@app.route("/events", methods=["GET", "POST"])
@login_required
def events():
    """Display all available events"""
    events = db.session.query(Class).order_by(Class.participants.desc()).all()
    relations = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).all()
    participants = {}
    for class in events:
        participants[class.id] = []
    for relation in relations:
        participants[relation[0].classs].append(relation[1])
    return render_template("events.html", events=events, error=check_error(), participants=participants, user=session)

@app.route("/event/<int:id>", methods=["GET", "POST"])
@login_required
def event(id):
    """Display summary of a class"""
    if request.method == "GET":
        event = db.session.query(Class).get(id)
        participants = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).filter(Relationship.classs == id)
        return render_template("event.html", event=event, error=check_error(), participants=participants, user=session)
    else:
        event = db.session.query(Class).get(id)
        event.participants += 1
        relation = Relationship(classs=event.id, participant=session.id)
        db.session.add(relation)
        db.session.commit()
        flash("")
        return redirect("/")

@app.route("/profile")
@login_required
def profile_own():
    return render_template("profile.html", profile=session, own=True, user=session)

@app.route("/profile/<int:id>")
@admin_required
@login_required
def profile(id):
    """Look up person's profile"""
    user = db.session.query(User).get(id)
    classes = db.session.query(Relationship, Class).join(Class, Class.id == Relationship.classs).filter(Relationship.participant == id).all()
    return render_template("profile.html", error=check_error(), profile=user, own=False, classes=classes, user=session)

@app.route("/profile/<int:id>/edit", methods=["GET", "POST"])
@admin_required
@login_required
def edit_person(id):
    """Edit person's profile"""
    user = db.session.query(User).get(id)
    if not user:
        flash("")
        return redirect(url_for("lookup", err="t"))
    if request.method == "GET":
        return render_template("user-edit.html", profile=user, user=session, error=check_error())
    else:
        user.first = request.form.get("first")
        user.last = request.form.get("last")
        user.email = request.form.get("email")
        user.role = request.form.get("role")
        user.subscribed = request.form.get("subscribed")
        db.session.commit()
        flash("Редагування успішне")
        return redirect(f"/profile/{id}")

@app.route("/lookup", methods=["GET", "POST"])
@admin_required
@login_required
def lookup():
    """Lookup a user form"""
    return render_template("lookup.html", error=check_error(), user=session)

@app.route("/create", methods=["GET", "POST"])
@admin_required
@login_required
def create():
    """Create an event"""
    if request.method == "GET":
        return render_template("create.html", user=session, error=check_error())
    else:
        event = Class(title=request.form.get("title"), start=request.form.get("start"), end=request.form.get("end"), capacity=request.form.get("capacity"), location=request.form.get("location"), trainer=request.form.get("trainer"))
        db.session.add(event)
        db.session.commit()
        flash("Заняття створено")
        return redirect(f"/event/{event.id}")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in using Google sign-in"""
    session["error"] = False
    if request.method == "POST":
        token = request.form["idtoken"]
        try:
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), G_CLIENT_ID)

            # ID token is valid. Get the user's Google Account ID from the decoded token.
            guserid = idinfo["sub"]
        except ValueError:
            # Invalid token
            pass
        user = User.query.filter_by(google_id=guserid).first()
        if not user:
            user = User(first=idinfo["given_name"], last=idinfo["family_name"], email=idinfo["email"], google_id=guserid, picture=idinfo["picture"])
            db.session.add(user)
            db.session.commit()
            user = User.query.filter_by(google_id=guserid).first()
        else:
            # Update existing info
            #user.first = idinfo["given_name"] # Probably will leave name editing up to staff
            #user.last=idinfo["family_name"]
            user.picture=idinfo["picture"]
            db.session.commit()
        session["id"] = user.id
        session["first"] = user.first
        session["last"] = user.last
        session["email"] = user.email
        session["role"] = user.role
        session["picture"] = user.picture
        return redirect("/")
    return render_template("login.html", error=session.get("error"), google_signin_client_id=G_CLIENT_ID, user=session)

if __name__ == "__main__":
    with app.app_context():
        app.run()