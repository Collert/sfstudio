from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__="users"
    id = db.Column(db.Integer, primary_key=True)
    pass_id = db.Column(db.Integer, nullable=False)
    first = db.Column(db.String, nullable=False)
    last = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=True) # Null if single-use
    google_id = db.Column(db.String, nullable=True) # Null if single-use
    role = db.Column(db.Integer, nullable=False, default=1)
    picture = db.Column(db.String, nullable=False, default="/static/nopic.jpg")
    subscribed = db.Column(db.Boolean, nullable=True, default=True) # Null if single-use
    tickets = db.Column(db.Integer, nullable=False)
    activation_date = db.Column(db.Date, nullable=True)
    called_sick = db.Column(db.Boolean, nullable=False, default=False)
    sick_start = db.Column(db.Date, nullable=True)
    # Single-use passes 
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
    trainer = db.Column(db.String, nullable=False)

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
    activation_date = db.Column(db.Date, nullable=False)

class Product(db.Model):
    __tablename__="products"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=False)
    price = db.Column(db.Numeric(2), nullable=True)

class PassTickets(db.Model):
    __tablename__="pass_tickets"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False)
    tickets = db.Column(db.Integer, nullable=False)