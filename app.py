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
SU_PASS_ID = 6942042069

##########
# Routes #
##########

@app.route("/")
def home():
    """Display homepage"""
    return render_template("home.html", error=check_error(), user=session, events=events)

@app.route("/events", methods=["GET", "POST"])
def events():
    """Display all available events"""
    events = db.session.query(Class, User).join(User, User.id == Class.coach).order_by(Class.start.desc(), Class.free.desc()).all()
    relations = db.session.query(Relationship, User).join(User, User.id == Relationship.participant).all()
    participants = {}
    for event in events:
        participants[event[0].id] = []
    for relation in relations:
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
            flash("Ви не ввійшли у ваш профіль")
            return redirect(url_for("home", err="t"))
        event = db.session.query(Class).get(id)
        if event.free < 1:
            flash("Заняття повне")
            return redirect(url_for(f"event({id})", err="t"))
        event.free -= 1
        relation = Relationship(classs=event.id, participant=session["id"])
        db.session.add(relation)
        db.session.commit()
        flash("Ви зареєструвалися на це заняття")
        return redirect("/")

@app.route("/event/new", methods=["GET", "POST"])
@login_required
@level_2
def create():
    """Create an event"""
    if request.method == "GET":
        coaches = db.session.query(User).filter(User.role >= 2).all()
        return render_template("create.html", user=session, error=check_error(), coaches=coaches)
    else:
        event = Class(title=request.form.get("title").strip(), start=request.form.get("start"), end=request.form.get("end"), capacity=request.form.get("capacity"), location=request.form.get("location"), coach=request.form.get("coach"), free=request.form.get("capacity"))
        db.session.add(event)
        db.session.commit()
        flash("Заняття створено")
        return redirect(f"/event/{event.id}")

@app.route("/profile")
@login_required
def profile_own():
    user = db.session.query(User).get(session["id"])
    events = db.session.query(Class, User, Relationship).join(User, User.id == Class.coach).join(Relationship, Relationship.classs == Class.id).filter(Relationship.participant == session["id"], Class.end > datetime.datetime.now()).all() # That's one scary query lmao
    pas = db.session.query(Pass).filter(Pass.owner == session["id"], Pass.addons == None).first()
    more = db.session.query(Pass, ProductAddon).join(ProductAddon, ProductAddon.id == Pass.addons).filter(Pass.owner == session["id"], Pass.addons != None).all()
    belt = db.session.query(Belt).filter(Belt.id == user.belt).first() if user.belt else None
    if pas:
        product = db.session.query(Product).filter(Product.tickets == pas.initial_tickets).first()
        days_left = (pas.activation_date + datetime.timedelta(days=PASS_EXPIRATION_PERIOD) - datetime.date.today()).days
        end_sick = pas.sick_start + datetime.timedelta(days=SICK_PERIOD) if pas.called_sick else None
    else:
        product = None
        days_left = None
        end_sick = None
    return render_template("profile.html", profile=user, own=True, user=session, error=check_error(), pas=pas, product=product, days_left=days_left, end_sick=end_sick, events=events, more=more, belt=belt)

@app.route("/call_sick/<int:id>", methods=["POST"])
@login_required
def call_sick(id):
    if session["id"] != id and session["role"] < 3:
        flash("Не достатньо привілегій щоб декларувати людину хворою. Cпробуйте знову з власним ID користувача.")
        return redirect(url_for("home", err="t"))
    pas = db.session.query(Pass).filter(Pass.owner == session["id"], Pass.addons == None).first()
    if not pas:
        flash("У даного користувача немає основного абонемента")
        return redirect(url_for("home", err="t"))
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
@login_required
@level_3
def profile(id):
    """Look up person's profile"""
    user = db.session.query(User).get(id)
    if not user:
        flash("Людини з даним ID не знайдено")
        return redirect(url_for("lookup", err="t"))
    events = db.session.query(Class, User, Relationship).join(User, User.id == Class.coach).join(Relationship, Relationship.classs == Class.id).filter(Relationship.participant == session["id"]).all() # That's one scary query lmao
    pas = db.session.query(Pass).filter(Pass.owner == id).first()
    more = db.session.query(Pass, Product).join(Product, Product.id == Pass.product).filter(Pass.owner == session["id"], Pass.addons != None).all()
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
@login_required
@level_3
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
            print(users)
        elif pass_num:
            users = db.session.query(User).filter(User.pass_id == pass_num).all()
        else:
            flash("Не надано жодної інформації")
            return redirect(url_for("lookup", err="t"))
        if not users:
            flash("Людини за даними параметрами не знайдено")
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
        flash("Абонемент додано")
        return redirect("/")

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
        flash("Абонементи оновлено")
        return redirect("/")

@app.route("/products")
@login_required
@level_4
def products():
    """Display all available products"""
    products = db.session.query(Product).all()
    user_virgin = db.session.query(Virgins).filter(Virgins.person == session["id"]).all() if session["id"] else None
    tried = []
    for product in user_virgin:
        tried.append(product.product)
    return render_template("products.html", error=check_error(), user=session, products=products, tried=tried)


@app.route("/products/<int:id>", methods=["GET", "POST"])
@login_required
@level_4
def product(id):
    """Display delected product"""
    if request.method == "GET":
        product = db.session.query(Product).get(id)
        return render_template("product.html", error=check_error(), user=session, product=product)
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
        db.session.commit()
        flash("Продукт редаговано")
        return redirect(f"/products/{id}")

@app.route("/products/new", methods=["GET", "POST"])
@login_required
@level_4
def new_product():
    """Create a new product"""
    if request.method == "GET":
        return render_template("product.html", error=check_error(), user=session, product=None)
    else: # Editing
        product = Product
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
        db.session.add(product)
        db.session.commit()
        flash("Продукт створено")
        return redirect(f"/products/{product.id}")

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
            flash("Абонемент не знайдено")
            return redirect(url_for("register", err="t"))
        elif pass_obj.single_use:
            flash("Ви ввели разовий абонемент. Будь-ласка увійдіть як разовий користувач.")
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
                flash("Абонемент не знайдено")
                return redirect(url_for("single_use", err="t"))
            if not pass_obj.single_use:
                flash("У вас постійний абонемент. Зареєструйтеся як постійний користувач.")
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