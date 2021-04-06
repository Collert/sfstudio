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
    role = db.Column(db.String, nullable=False, default="customer")
    picture = db.Column(db.String, nullable=False, default="/static/nopic.jpg")
    subscribed = db.Column(db.Boolean, nullable=True, default=True) # Null if single-use
    # Single-use passes 
    single_use = db.Column(db.Boolean, nullable=False, default=False)
    tickets = db.Column(db.Integer, nullable=True) # Null if regular customer

class Class(db.Model):
    __tablename__="classes"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    start = db.Column(db.Date, nullable=False)
    end = db.Column(db.Date, nullable=False)
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