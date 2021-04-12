from functools import singledispatch
from http.client import error
from logging import log
from operator import sub
from re import U
from tempfile import mkdtemp
import os
from threading import Event
import datetime
import csv
import codecs

from sqlalchemy import create_engine, or_, and_, sql
from sqlalchemy.ext.declarative.api import as_declarative
from sqlalchemy.orm import query, relation, relationship, scoped_session, sessionmaker
from flask import Flask, flash, redirect, render_template, request, session, jsonify, make_response, send_from_directory, url_for
from flask_session import Session
from sqlalchemy.sql.expression import true
from sqlalchemy.sql.functions import user
from werkzeug.datastructures import ViewItems
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
SICK_PERIOD = 7 # Days
PASS_EXPIRATION_PERIOD = 30 # Days
COACH_COEFICIENT = 0.5
SU_PASS_ID = 6942042069

##########
# Routes #
##########

@app.route("/")
def home():
    """Display homepage"""
    events = db.session.query(Relationship, Class).join(Class, Class.id == Relationship.classs).filter(Relationship.participant == 1).all()
    return render_template("home.html", error=check_error(), user=session, events=events)

@app.route("/events", methods=["GET", "POST"])
def events():
    """Display all available events"""
    events = db.session.query(Class).order_by(Class.start.desc(), Class.free.desc()).all()
    relations = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).all()
    participants = {}
    for event in events:
        participants[event.id] = []
    for relation in relations:
        participants[relation[0].classs].append(relation[1])
    return render_template("events.html", events=events, error=check_error(), participants=participants, user=session)

@app.route("/event/<int:id>", methods=["GET", "POST"])
def event(id):
    """Display summary of a class"""
    if request.method == "GET":
        event = db.session.query(Class).get(id)
        participants = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).filter(Relationship.classs == id)
        return render_template("event.html", event=event, error=check_error(), participants=participants, user=session)
    else:
        if not session.id:
            flash("Ви не ввійшли у ваш профіль")
            return redirect(url_for("home", err="t"))
        event = db.session.query(Class).get(id)
        event.free -= 1
        relation = Relationship(classs=event.id, participant=session.id)
        db.session.add(relation)
        db.session.commit()
        flash("Ви зареєструвалися на це заняття")
        return redirect("/")

@app.route("/event/new", methods=["GET", "POST"])
@level_2
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

@app.route("/call_sick/<int:id>", methods=["POST"])
@login_required
def call_sick(id):
    if session["id"] != id and session["role"] < 3:
        flash("Не достатньо привілегій щоб декларувати людину хворою. Cпробуйте знову з власним ID користувача.")
        return redirect(url_for("home", err="t"))
    pas = db.session.query(Pass).filter(Pass.owner == session["id"])
    if pas.tickets < 1:
        flash("Ваш абонемент не активний")
        return redirect(url_for("home", err="t"))
    pas.called_sick = True
    date = request.form.get("date")
    if date:
        if date > pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD):
            flash("Введена вами дата знаходиться після завершення вашого абонементу. Будь-ласка виберіть іншу дату.")
            return redirect(url_for("home", err="t"))
        pas.sick_start = date
    else:
        pas.sick_start = datetime.date.today()
    db.session.commit()
    flash("Абонемент заморожено. Бажаємо швидкого одужання!")
    return redirect(url_for("home"))

@app.route("/profile/<int:id>")
@level_3
@login_required
def profile(id):
    """Look up person's profile"""
    user = db.session.query(User).get(id)
    if not user:
        flash("Людини з даним ID не знайдено")
        return redirect(url_for("lookup", err="t"))
    classes = db.session.query(Relationship, Class).join(Class, Class.id == Relationship.classs).filter(Relationship.participant == id).all()
    return render_template("profile.html", error=check_error(), profile=user, own=False, classes=classes, user=session)

@app.route("/profile/<int:id>/edit", methods=["GET", "POST"])
@level_3
@login_required
def edit_person(id):
    """Edit person's profile"""
    user = db.session.query(User).get(id)
    if not user:
        flash("Людини з даним ID не знайдено")
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
@level_3
@login_required
def lookup():
    """Lookup a user form"""
    if request.method == "GET":
        return render_template("lookup.html", error=check_error(), user=session)
    else:
        first = f"%{request.form.get('first')}%"
        last = f"%{request.form.get('last')}%"
        email = request.form.get('email')
        pass_num = request.form.get('pass_num')
        if first and last:
            users = db.session.query(User).filter(User.first.ilike(first), User.last.ilike(last)).all()
        elif first:
            users = db.session.query(User).filter(User.first.ilike(first)).all()
        elif last:
            users = db.session.query(User).filter(User.last.ilike(last)).all()
        elif email:
            users = db.session.query(User).filter(User.email == email).all()
        elif pass_num:
            users = db.session.query(User).filter(User.pass_id == pass_num).all()
        if not users:
            flash("Людини за даними параметрами не знайдено")
            return redirect(url_for("lookup", err="t"))
        else:
            return render_template("lookup.html", error=check_error(), user=session, users=users)

@app.route("/pass/new/<int:id>", methods=["GET", "POST"])
@level_3
@login_required
def new_pass(id):
    if id == SU_PASS_ID:
        single_use = True
    else:
        single_use = False
    if request.method == "GET":
        tried_products = db.session.query(Virgins).filter(Virgins.person == id).all()
        products = db.session.query(Product).all()
        subject = db.session.query(User).get(id)
        return render_template("new_pass.html", error=check_error(), user=session, products=products, tried_products=tried_products, subject=subject)
    else:
        tickets = request.form.get("tickets")
        price = request.form.get("price")
        activation = datetime.date.today()
        if single_use:
            first = request.form.get("first")
            last = request.form.get("last")
            owner = None
        else:
            user = db.session.query(User).get(id)
            if not user:
                flash("User does not exist")
                return redirect(url_for("lookup", err="t"))
            first = user.first
            last = user.last
            owner = user.id
        new_pass = Pass(first=first, last=last, single_use=single_use, tickets=tickets, value=price, activation_date=activation, owner=owner, initial_tickets=tickets)
        db.session.add(new_pass)
        if not single_use:
            user.pass_id = new_pass.id
        db.session.commit()
        flash("Абонемент додано")
        return redirect("/")

@app.route("/pass/activate/mass")
@level_3
@login_required
def mass_activate():
    """
    REDUNDANT
    Mass update users and deactivate the ones who didn't pay the monthly fee
    """
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
        try:
            idinfo = session["google_creds"]
            guserid = idinfo["sub"]
        except KeyError:
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
            session["google_creds"] = idinfo
            return redirect("/register")
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
        return redirect("/")
    return render_template("login.html", error=check_error(), google_signin_client_id=G_CLIENT_ID, user=session)
    
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a user if a pass is available"""
    if request.method == "GET":
        return render_template("register.html", error=check_error())
    else:
        pass_id = request.form.get("pass_id")
        pass_obj = db.session.query(Pass).filter(Pass.id == pass_id).first()
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

@app.cli.command("expire_pass")
def expire_pass():
    """Remove all remaining tickets from user if not used within a month"""
    users = db.session.query(User).all()
    today = datetime.date.today()
    for user in users:
        exp_date = user.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD)
        if today < exp_date:
            continue
        elif user.called_sick and today < (exp_date + datetime.timedelta(days=SICK_PERIOD)):
            continue
        user.tickets = 0
        user.pass_id = None
        pas = db.session.query(Pass).get(user.pass_id)
        if pas:
            db.session.delete(pas)
        db.session.commit()
    passes = db.session.query(Pass).all()
    for pas in passes:
        exp_date = pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD)
        if today < exp_date:
            continue
        elif pas.called_sick and today < (exp_date + datetime.timedelta(days=SICK_PERIOD)):
            continue
        db.session.delete(pas)
        db.session.commit()

@app.cli.command("financial_report")
def financial_report():
    """Display monthly financial report"""
    today = datetime.date.today()
    month_ago = today - datetime.timedelta(days=30)
    coaches = db.session.query(User).filter(User.role == 2).all()
    payouts = {}
    for coach in coaches:
        payouts[coach.id] = {}
        money = float(0)
        classes = db.session.query(Class).filter(Class.coach == coach.id, Class.start > month_ago).all()
        for clas in classes:
            relations = db.session.query(Relationship).filter(Relationship.classs == clas.id).all()
            for participant in relations:
                pas = db.session.query(Pass).filter(Pass.owner == participant.participant).first()
                used_times = pas.initial_tickets - pas.tickets
                add = pas.value / used_times * COACH_COEFICIENT
                money += add
        payouts[coach.id]["id"] = coach.id
        payouts[coach.id]["first"] = coach.first
        payouts[coach.id]["last"] = coach.last
        payouts[coach.id]["ammount"] = round(money, 2)

if __name__ == "__main__":
    with app.app_context():
        app.run()