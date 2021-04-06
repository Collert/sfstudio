from http.client import error
from logging import log
from re import U
from tempfile import mkdtemp
import os
from threading import Event
import datetime
import csv
import codecs

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
    for event in events:
        participants[event.id] = []
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

@app.route("/event/new", methods=["GET", "POST"])
@coach_required
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

@app.route("/profile")
@login_required
def profile_own():
    return render_template("profile.html", profile=session, own=True, user=session, error=check_error())

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

@app.route("/pass/new", methods=["GET", "POST"])
@admin_required
@login_required
def new_pass():
    if request.method == "GET":
        return render_template("new_pass.html", error=check_error(), user=session)
    else:
        new_pass = Pass(id=request.form.get("pass_id"), first=request.form.get("first"), last=request.form.get("last"), single_use=request.form.get("single_use"))
        db.session.add(new_pass)
        db.session.commit()
        flash("Абонемент додано")
        return redirect("/")

@app.route("/pass/activate/mass")
@admin_required
@login_required
def mass_activate():
    if request.method == "GET":
        return render_template("mass_activate.html", error=check_error(), user=session)
    else:
        if 'file' not in request.files:
            flash('No file part')
            return redirect(url_for("mass_activate", err="t"))
        list = request.files["list"]
        if list and allowed_file(list.filename):
            paid = []
            stream = codecs.iterdecode(list.stream, 'utf-8')
            for row in csv.reader(stream, dialect=csv.excel):
                if row:
                    paid.append(row)
        users = db.session.query(User).all()
        if paid:
            for user in users:
                if user.pass_id in paid:
                    user.subscribed = True
                else:
                    user.subscribed = False
                db.session.commit()
        flash("Абонементи оновлено")
        return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in using Google sign-in"""
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
        print("=====================================================================================================================")
        print(user.first)
        print("=====================================================================================================================")
        if not user:
            session["google_creds"] = idinfo
            return redirect(url_for("register"))
        else:
            # Update existing info
            user.picture=idinfo["picture"]
            db.session.commit()
        session["id"] = user.id
        session["first"] = user.first
        session["last"] = user.last
        session["email"] = user.email
        session["role"] = user.role
        session["picture"] = user.picture
        session["pass_id"] = user.pass_id
        session["subscribed"] = user.subscribed
        session["single_use"] = user.single_use
        session["tickets"] = user.tickets
        return redirect("/")
    return render_template("login.html", error=session.get("error"), google_signin_client_id=G_CLIENT_ID, user=session)
    
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a user if a pass is available"""
    if request.method == "GET":
        return render_template("register.html", error=check_error())
    else:
        pass_id = request.form.get("pass_id")
        pass_obj = Pass.query.get(pass_id)
        if not pass_obj:
            flash("Абонемент не знайдено")
            return redirect(url_for("register", err="t"))
        elif pass_obj.single_use:
            flash("Ви ввели разовий абонемент. Будь-ласка увійдіть як разовий користувач.")
            return redirect(url_for("single_use"))
        else:
            idinfo = session["google_creds"]
            user = User(first=idinfo["given_name"], pass_id=pass_obj.id, last=idinfo["family_name"], email=idinfo["email"], google_id=idinfo["sub"], picture=idinfo["picture"])
            db.session.add(user)
            db.session.delete(pass_obj)
            db.session.commit()
            session["id"] = user.id
            session["first"] = user.first
            session["last"] = user.last
            session["email"] = user.email
            session["role"] = user.role
            session["picture"] = user.picture
            session["pass_id"] = user.pass_id
            session["subscribed"] = user.subscribed
            session["single_use"] = user.single_use
            session["tickets"] = user.tickets
            return redirect("/")
        
@app.route("/single_use", methods=["GET", "POST"])
def single_use():
    """Log a person in with a single use pass"""
    if request.method == "GET":
        return render_template("single_use.html", error=check_error())
    else:
        user = db.session.query(User).filter(User.pass_id == request.form.get("pass_id")).first()
        if not user:
            pass_obj = Pass.query.get(request.form.get("pass_id"))
            if not pass_obj:
                flash("Абонемент не знайдено")
                return redirect(url_for("single_use", err="t"))
            else:
                user = User(first=pass_obj.first, pass_id=pass_obj.id, last=pass_obj.last, email=None, google_id=None, single_use=True, tickets=pass_obj.tickets)
                db.session.add(user)
                db.session.delete(pass_obj)
                db.session.commit()
        session["id"] = user.id
        session["first"] = user.first
        session["last"] = user.last
        session["email"] = user.email
        session["role"] = user.role
        session["picture"] = user.picture
        session["pass_id"] = user.pass_id
        session["subscribed"] = user.subscribed
        session["single_use"] = user.single_use
        session["tickets"] = user.tickets
        return redirect("/")

##############
# Automation #
##############

@app.cli.command("delete_single_use")
def delete_single_use():
    """Delete empty single-use accounts on the first day of the month"""
    if datetime.date.today().day == 1:
        single_users = db.session.query(User).filter(User.single_use == True).all()
        for user in single_users:
            if db.session.query(Relationship).filter(Relationship.participant == user.id).first():
                # Skip deletion if user is still registered for a class
                continue
            if user.tickets > 0:
                continue
            else:
                db.session.delete(user)
        db.session.commit()

@app.cli.command("delete_old_class")
def delete_old_class():
    """Delete classes that are over 90 days old"""
    three_months_old = datetime.date.today() - datetime.timedelta(days=90)
    old_classes = db.session.query(Class).filter(Class.end < three_months_old).all()
    for event in old_classes:
        db.session.delete(event)
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        app.run()