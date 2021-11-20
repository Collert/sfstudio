from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__="users"
    id = db.Column(db.Integer, primary_key=True)
    pass_id = db.Column(db.Integer, nullable=True)
    first = db.Column(db.String, nullable=False)
    last = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=True) # Null if single-use
    google_id = db.Column(db.String, nullable=True) # Null if single-use
    role = db.Column(db.Integer, nullable=False, default=1)
    picture = db.Column(db.String, nullable=False, default="/static/nopic.jpg")
    subscribed = db.Column(db.Boolean, nullable=True, default=True) # Null if single-use
    belt = db.Column(db.Integer, nullable=True) # Null if not staff
    # Single-use passes 
    tickets = db.Column(db.Integer, nullable=True)
    single_use = db.Column(db.Boolean, nullable=False, default=False)

class Class(db.Model):
    __tablename__="classes"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    free = db.Column(db.Integer, nullable=False, default=0)
    location = db.Column(db.String, nullable=False)
    coach = db.Column(db.Integer, nullable=False)
    private = db.Column(db.Boolean, nullable=False, default=False)

class Relationship(db.Model):
    __tablename__="relations"
    id = db.Column(db.Integer, primary_key=True)
    participant = db.Column(db.Integer, nullable=False)
    classs = db.Column(db.Integer, nullable=False)

class Pass(db.Model):
    __tablename__="passes"
    id = db.Column(db.Integer, primary_key=True)
    first = db.Column(db.String, nullable=False)
    last = db.Column(db.String, nullable=False)
    single_use = db.Column(db.Boolean, nullable=False, default=False)
    tickets = db.Column(db.Integer, nullable=True, default=1)
    value = db.Column(db.Numeric, nullable=False)
    activation_date = db.Column(db.Date, nullable=False)
    called_sick = db.Column(db.Boolean, nullable=False, default=False)
    sick_start = db.Column(db.Date, nullable=True)
    owner = db.Column(db.Integer, nullable=True) # Null if unclaimed single-use
    initial_tickets = db.Column(db.Integer, nullable=False)
    addons = db.Column(db.Integer, nullable=True) # Null if a pass with no addons
    product = db.Column(db.Integer, nullable=False)

class ProductAddon(db.Model):
    __tablename__="addons"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

class Product(db.Model):
    __tablename__="products"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=False)
    price = db.Column(db.Numeric, nullable=True)
    virgin = db.Column(db.Numeric, nullable=True)
    price_from = db.Column(db.Numeric, nullable=True)
    virgin_from = db.Column(db.Numeric, nullable=True)
    tickets = db.Column(db.Integer, nullable=True)
    addon = db.Column(db.Integer, nullable=True)

class Virgins(db.Model):
    __tablename__="virgins"
    person = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.Integer, nullable=False)

class Belt(db.Model):
    __tablename__="badges"
    id = db.Column(db.Integer, primary_key=True)
    person = db.Column(db.Integer, nullable=False)
    coach = db.Column(db.Boolean, nullable=False, default=False)
    dietitian = db.Column(db.Boolean, nullable=False, default=False)

class EventRequest(db.Model):
    __tablename__="requests"
    id = db.Column(db.Integer, primary_key=True)
    creator = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String, nullable=False)
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String, nullable=False)
    coach = db.Column(db.Integer, nullable=False)
    accepted = db.Column(db.Boolean, nullable=True, default=None) # NULL if the request hasn't recieved a response yet
    reason = db.Column(db.String, nullable=True, default=None) # Reason for declining the booking

class Notification(db.Model):
    __tablename__="notifications"
    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String, nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    read = db.Column(db.Boolean, nullable=False, default=False)
    category = db.Column(db.Integer, nullable=False)
    ######################################################
    # Notification categories (display different icons): #
    # 1 = class related                                  #
    # 2 = pass related                                   #
    ######################################################