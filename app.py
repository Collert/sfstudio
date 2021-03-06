from functools import singledispatch
from http.client import error
from logging import log
from operator import sub
from re import U
import re
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
SU_PASS_ID = 6942069
DIETARY_CONSULTATION_DURAION = 30 # Minutes
PERSONAL_COACHING_SESSION_DURATION = 60 # Minutes

##########
# Routes #
##########

@app.route("/")
def home():
    """Display homepage"""
    return render_template("home.html", error=check_error(), user=session)

@app.route("/events", methods=["GET", "POST"])
def events():
    """Display all available events"""
    events = db.session.query(Class, User).join(User, User.id == Class.coach).filter(Class.private == False).order_by(Class.start.desc(), Class.free.desc()).all()
    private_events = db.session.query(Class).filter(Class.private == True).all()
    private_classes = []
    for event in private_events:
        private_classes.append(event.id)
    relations = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).all()
    participants = {}
    for event in events:
        participants[event[0].id] = []
    for relation in relations:
        if relation[0].classs in private_classes:
            continue
        participants[relation[0].classs].append(relation[1])
    return render_template("events.html", events=events, error=check_error(), participants=participants, user=session)

@app.route("/event/<int:id>", methods=["GET", "POST"])
def event(id):
    """Display summary of a class"""
    if request.method == "GET":
        event = db.session.query(Class).get(id)
        participants = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).filter(Relationship.classs == id).all()
        coach = db.session.query(User).get(event.coach)
        return render_template("event.html", event=event, error=check_error(), participants=participants, user=session, coach=coach)
    else:
        if not session["id"]:
            flash("???? ???? ?????????????? ?? ?????? ??????????????")
            return redirect(url_for("home", err="t"))
        event = db.session.query(Class).get(id)
        if event.free < 1:
            flash("?????????????? ??????????")
            return redirect(url_for(f"event({id})", err="t"))
        event.free -= 1
        relation = Relationship(classs=event.id, participant=session["id"])
        db.session.add(relation)
        db.session.commit()
        remove_ticket(session["id"], None)
        flash("???? ?????????????????????????????? ???? ???? ??????????????")
        return redirect(url_for("events"))

@app.route("/event/new", methods=["GET", "POST"])
@login_required
@level_2
def create():
    """Create an event"""
    if request.method == "GET":
        belts = db.session.query(Belt).filter(Belt.coach == True).all()
        staff = db.session.query(User).filter(User.role >= 2).all()
        belts_ids = []
        coaches = []
        for belt in belts:
            belts_ids.append(belt.person)
        for coach in staff:
            if coach.id in belts_ids:
                coaches.append(coach)
        return render_template("create.html", user=session, error=check_error(), coaches=coaches, booking=False)
    else:
        event = create_event(request.form.get("title").strip(), request.form.get("start"), request.form.get("end"), request.form.get("capacity"), request.form.get("location"), request.form.get("coach"), False)
        flash("?????????????? ????????????????")
        return redirect(f"/event/{event.id}")

@app.route("/profile")
@login_required
def profile_own():
    user = db.session.query(User).get(session["id"])
    events = db.session.query(Class, User, Relationship).join(User, User.id == Class.coach).join(Relationship, Relationship.classs == Class.id).filter(Relationship.participant == session["id"], Class.end > datetime.datetime.now()).all() # That's one scary query lmao
    coached = db.session.query(Class, User).join(User, User.id == Class.coach).filter(Class.coach == session["id"], Class.end > datetime.datetime.now()).all()
    for classs in coached:
        events.append(classs)
    if user.pass_id:
        pas = db.session.query(Pass).get(user.pass_id)
        pas = None if pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD) < datetime.date.today() else pas
    else:
        pas = None
    more = db.session.query(Pass, ProductAddon).join(ProductAddon, ProductAddon.id == Pass.addons).filter(Pass.owner == session["id"], Pass.addons != None, Pass.tickets > 0).all()
    belt = db.session.query(Belt).filter(Belt.id == user.belt).first() if user.belt else None
    if pas:
        product = db.session.query(Product).filter(Product.tickets == pas.initial_tickets).first()
        days_left = (pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD) - datetime.date.today()).days
        end_sick = pas.sick_start + datetime.timedelta(days=SICK_PERIOD) if pas.called_sick else None
    else:
        product = None
        days_left = None
        end_sick = None
    notifications = len(check_user_notifications(session["id"]))
    return render_template("profile.html", profile=session, own=True, user=session, error=check_error(), pas=pas, product=product, days_left=days_left, end_sick=end_sick, events=events, more=more, belt=belt)

@app.route("/call_sick/<int:id>", methods=["POST"])
@login_required
def call_sick(id):
    if session["id"] != id and session["role"] < 3:
        flash("???? ?????????????????? ???????????????????? ?????? ?????????????????????? ???????????? ????????????. C???????????????? ?????????? ?? ?????????????? ID ??????????????????????.")
        return redirect(url_for("home", err="t"))
    pas = db.session.query(Pass).filter(Pass.owner == id, Pass.addons == None).first()
    if not pas:
        flash("???? ???????????????? ???????????????????? ????'?????????????? ?? ?????? ????????????????")
        return redirect(url_for(f"profile({id})", err="t"))
    if pas.tickets < 1:
        flash("?????? ?????????????????? ???? ????????????????")
        return redirect(url_for("home", err="t"))
    pas.called_sick = True
    date = request.form.get("date")
    if date:
        if date > pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD):
            flash("?????????????? ???????? ???????? ?????????????????????? ?????????? ???????????????????? ???????????? ????????????????????. ????????-?????????? ???????????????? ???????? ????????.")
            return redirect(url_for("home", err="t"))
        pas.sick_start = date
    else:
        pas.sick_start = datetime.date.today()
    db.session.commit()
    flash("?????????????????? ????????????????????. ?????????????? ???????????????? ????????????????!")
    return redirect(url_for("home"))

@app.route("/profile/<int:id>")
@login_required
@level_3
def profile(id):
    """Look up person's profile"""
    user = db.session.query(User).get(id)
    if not user:
        flash("???????????? ?? ?????????? ID ???? ????????????????")
        return redirect(url_for("lookup", err="t"))
    events = db.session.query(Class, User, Relationship).join(User, User.id == Class.coach).join(Relationship, Relationship.classs == Class.id).filter(Relationship.participant == session["id"]).all() # That's one scary query lmao
    pas = db.session.query(Pass).filter(Pass.owner == id).first()
    more = db.session.query(Pass, Product).join(Product, Product.id == Pass.product).filter(Pass.owner == id, Pass.addons != None).all()
    belt = db.session.query(Belt).filter(Belt.id == user.belt).first() if user.belt else None
    if pas:
        product = db.session.query(Product).filter(Product.tickets == pas.initial_tickets).first()
        days_left = (pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD) - datetime.date.today()).days
        end_sick = pas.sick_start + datetime.timedelta(days=SICK_PERIOD) if pas.called_sick else None
    else:
        product = None
        days_left = None
        end_sick = None
    return render_template("profile.html", profile=user, own=False, user=session, error=check_error(), pas=pas, product=product, days_left=days_left, end_sick=end_sick, events=events, more=more, belt=belt)

@app.route("/profile/<int:id>/edit", methods=["GET", "POST"])
@login_required
@level_3
def edit_person(id):
    """Edit person's profile"""
    user = db.session.query(User).get(id)
    if not user:
        flash("???????????? ?? ?????????? ID ???? ????????????????")
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
        flash("?????????????????????? ??????????????")
        return redirect(f"/profile/{id}")

@app.route("/lookup", methods=["GET", "POST"])
@login_required
@level_2
def lookup():
    """Lookup a user form"""
    if request.method == "GET":
        return render_template("lookup.html", error=check_error(), user=session)
    else:
        first = request.form.get('first')
        last = request.form.get('last')
        email = request.form.get('email')
        pass_num = request.form.get('pass_num')
        if first and last:
            first = f"%{first}%"
            last = f"%{last}%"
            users = db.session.query(User).filter(User.first.ilike(first), User.last.ilike(last)).all()
        elif first:
            first = f"%{first}%"
            users = db.session.query(User).filter(User.first.ilike(first)).all()
        elif last:
            last = f"%{last}%"
            users = db.session.query(User).filter(User.last.ilike(last)).all()
        elif email:
            users = db.session.query(User).filter(User.email == email).all()
        elif pass_num:
            users = db.session.query(User).filter(User.pass_id == pass_num).all()
        else:
            flash("???? ???????????? ???????????? ????????????????????")
            return redirect(url_for("lookup", err="t"))
        if not users:
            flash("???????????? ???? ???????????? ?????????????????????? ???? ????????????????")
            return redirect(url_for("lookup", err="t"))
        else:
            return render_template("lookup_results.html", error=check_error(), user=session, users=users)

@app.route("/pass/new/<int:id>", methods=["GET", "POST"])
@login_required
@level_3
def new_pass(id):
    if id == SU_PASS_ID:
        single_use = True
    else:
        single_use = False
    if request.method == "GET":
        subject = db.session.query(User).get(id) if not single_use else None
        tried_products = db.session.query(Virgins).filter(Virgins.person == id).all()
        tried = []
        products = db.session.query(Product).all()
        for product in tried_products:
            tried.append(product.product)
        user_pricelist = {}
        for unit in products:
            product = {}
            product["id"] = unit.id
            product["title"] = unit.title
            product["description"] = unit.description
            product["tickets"] = unit.tickets
            if unit.id in tried:
                product["price"] = float(unit.price if unit.price else (unit.price_from if unit.price_from else 0))
            else:
                product["price"] = float(unit.virgin if unit.virgin else (unit.virgin_from if unit.virgin_from else 0))
            user_pricelist[unit.id] = product
        return render_template("new_pass.html", error=check_error(), user=session, products=user_pricelist, tried_products=tried_products, subject=subject)
    else:
        product = request.form.get("product")
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
        new_pass = Pass(first=first, last=last, single_use=single_use, tickets=tickets, product=product, value=price, activation_date=activation, owner=owner, initial_tickets=tickets)
        db.session.add(new_pass)
        db.session.commit()
        if not single_use:
            user.pass_id = new_pass.id
        db.session.commit()
        if not single_use:
            make_notification(user.id, f"?????????????????????????? {session['first']} {session['last']} ??????????(????) ??????????????????: {(db.session.query(Product).filter(Product.id == product).first()).title} ???? ???????????? ???????????????????? ????????????")
        flash("?????????????????? ????????????")
        return redirect("/")

@app.route("/book/<addon>", methods=["GET", "POST"])
@login_required
def book_private_class(addon):
    """Book a 1:1 session with any of qualified coaches"""
    if request.method == "GET":
        if addon == "4":
            belts = db.session.query(Belt).filter(Belt.dietitian == True).all()
            title = f"???????????????????????? ???????????????????????? ?? {session['first']}"
        elif addon == "3":
            belts = db.session.query(Belt).filter(Belt.coach == True).all()
            title = f"1:1 ???????????????????? ?? {session['first']}"
        else:
            flash("Unknown specialist role")
            return redirect(url_for("profile_own", err="t"))
        staff = db.session.query(User).filter(User.role >= 2).all()
        belts_ids = []
        specialists = []
        for belt in belts:
            belts_ids.append(belt.person)
        for coach in staff:
            if coach.id in belts_ids:
                specialists.append(coach)
        return render_template("create.html", error=check_error(), user=session, coaches=specialists, booking=True, title=title, id=addon)
    else:
        title = request.form.get("title").strip()
        print(request.form.get("start"))
        start = datetime.datetime.fromisoformat(request.form.get("start"))
        if addon == "4":
            end = start + datetime.timedelta(minutes=DIETARY_CONSULTATION_DURAION)
        else:
            end = start + datetime.timedelta(minutes=PERSONAL_COACHING_SESSION_DURATION)
        location = request.form.get("location")
        coach = request.form.get("coach")
        create_event_request(session["id"], title, start, end, location, coach)
        coach = db.session.query(User).get(coach)
        flash(f"?????????? ?????????????????? ??????????????: {coach.first} {coach.last}")
        return redirect(url_for("profile_own"))

@app.route("/book/<int:id>/<response>", methods=["POST"])
@login_required
@level_2
def booking_response(id, response):
    """Respond to a 1:1 request to a specialist"""
    event = db.session.query(EventRequest).filter(EventRequest.id == id).first()
    agree = True if response == "accept" else False
    if agree:
        event.accepted = True
        event_out = create_event(event.title, event.start, event.end, 0, event.location, session["id"], True)
        register_for_event(event.creator, event.id)
        flash("???? ???????????????????? ???????????????? ???? ??????????????")
        return redirect(f"/event/{event_out.id}")
    else:
        event.accepted = False
        event.reason = request.form.get("reason")
        db.session.commit()
        flash("???? ?????????????????????? ?????????????????? ???? ??????????????")
        return redirect(url_for("check_bookings"))

@app.route("/requests")
@login_required
@level_2
def check_bookings():
    """Coaches' way to check for requests for 1:1s"""
    requests = db.session.query(EventRequest, User).join(User, EventRequest.creator == User.id).filter(EventRequest.coach == session["id"], EventRequest.accepted == None).all()
    return render_template("requests.html", error=check_error(), user=session, requests=requests)

@app.route("/pass/activate/mass")
@login_required
@level_3
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
        flash("???????????????????? ????????????????")
        return redirect("/")

@app.route("/products")
def products():
    """Display all available products"""
    products = db.session.query(Product).all()
    try:
        user_virgin = db.session.query(Virgins).filter(Virgins.person == session["id"]).all()
    except KeyError:
        user_virgin = []
    tried = []
    for product in user_virgin:
        tried.append(product.product)
    return render_template("products.html", error=check_error(), user=session, products=products, tried=tried)

@app.route("/products/<int:id>", methods=["GET", "POST"])
@login_required
@level_4
def product(id):
    """Display selected product"""
    if request.method == "GET":
        product = db.session.query(Product).get(id)
        addons = db.session.query(ProductAddon).all()
        return render_template("product.html", error=check_error(), user=session, addons=addons, product=product)
    else: # Editing
        product = db.session.query(Product).get(id)
        product.title = (request.form.get("title")).strip()
        product.description = (request.form.get("description")).strip()
        if request.form.get("price-from"):
            product.price = None
            product.price_from = request.form.get("price")
        else:
            product.price_from = None
            product.price = request.form.get("price")
        if request.form.get("virgin-from"):
            product.virgin = None
            product.virgin_from = request.form.get("virgin")
        else:
            product.virgin_from = None
            product.virgin = request.form.get("virgin")
        product.tickets = request.form.get("tickets")
        product.addon = request.form.get("addon")
        db.session.commit()
        flash("?????????????? ????????????????????")
        return redirect(f"/products/{id}")

@app.route("/products/new", methods=["GET", "POST"])
@login_required
@level_4
def new_product():
    """Create a new product"""
    if request.method == "GET":
        addons = db.session.query(ProductAddon).all()
        return render_template("product.html", error=check_error(), user=session, product=None, addons=addons)
    else: # Editing
        product = Product()
        product.title = request.form.get("title")
        product.description = request.form.get("description")
        if request.form.get("price-from"):
            product.price_from = request.form.get("price")
        else:
            product.price = request.form.get("price")
        if request.form.get("virgin-from"):
            product.virgin_from = request.form.get("virgin")
        else:
            product.virgin = request.form.get("virgin")
        product.tickets = request.form.get("tickets")
        product.addon = request.form.get("addon")
        db.session.add(product)
        db.session.commit()
        flash("?????????????? ????????????????")
        return redirect(f"/products/{product.id}")

@app.route("/deletepass/<int:id>", methods=["GET", "POST"])
@login_required
@level_4
def delete_product(id):
    """Delete a product"""
    product = db.session.query(Product).get(id)
    db.session.delete(product)
    db.session.commit()
    flash("?????????????? ????????????????")
    return redirect("/products")

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
                session["google_creds"] = idinfo
                print(f"User logged in: {idinfo['given_name']} {idinfo['family_name']}: {idinfo['email']}")
                return "lol"
            except ValueError:
                # Invalid token
                pass
        user = User.query.filter_by(google_id=guserid).first()
        if user.role == 2:
            session["booking_requests"] = len(check_booking_requests(user.id))
            session["notification_count"] = None
        else:
            session["notification_count"] = len(check_user_notifications(user.id))
        if not user:
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
        return redirect(url_for("home"))
    return render_template("login.html", error=check_error(), google_signin_client_id=G_CLIENT_ID, user=session)
    
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a user if a pass is available"""
    if request.method == "GET":
        return render_template("register.html", error=check_error(), user=session)
    else:
        pass_id = request.form.get("pass_id")
        pass_obj = db.session.query(Pass).filter(Pass.id == pass_id).first()
        if not pass_obj:
            flash("?????????????????? ???? ????????????????")
            return redirect(url_for("register", err="t"))
        elif pass_obj.single_use:
            flash("???? ?????????? ?????????????? ??????????????????. ????????-?????????? ???????????????? ???? ?????????????? ????????????????????.")
            return redirect(url_for("single_use"))
        else:
            idinfo = session["google_creds"]
            user = User(first=idinfo["given_name"], pass_id=pass_obj.id, last=idinfo["family_name"], email=idinfo["email"], google_id=idinfo["sub"], picture=idinfo["picture"])
            db.session.add(user)
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
        return render_template("single_use.html", error=check_error(), user=session)
    else:
        user = db.session.query(User).filter(User.pass_id == request.form.get("pass_id")).first()
        if not user:
            pass_obj = Pass.query.get(request.form.get("pass_id"))
            if not pass_obj:
                flash("?????????????????? ???? ????????????????")
                return redirect(url_for("single_use", err="t"))
            if not pass_obj.single_use:
                flash("?? ?????? ?????????????????? ??????????????????. ???????????????????????????? ???? ?????????????????? ????????????????????.")
                return redirect(url_for("login", err="t"))
            user = User(first=pass_obj.first, pass_id=pass_obj.id, last=pass_obj.last, email=None, google_id=None, single_use=True, tickets=pass_obj.tickets)
            db.session.add(user)
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