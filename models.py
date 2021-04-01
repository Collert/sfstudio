from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__="users"
    id = db.Column(db.Integer, primary_key=True)
    first = db.Column(db.String, nullable=False)
    last = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False)
    google_id = db.Column(db.String, nullable=False)
    role = db.Column(db.String, nullable=False, default="customer")
    picture = db.Column(db.String, nullable=False, default="/static/nopic.jpg")
    subscribed = db.Column(db.Boolean, nullable=False, default=False)

class Class(db.Model):
    __tablename__="classes"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String, nullable=False)
    start = db.Column(db.Date, nullable=False)
    end = db.Column(db.Date, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    participants = db.Column(db.Integer, nullable=False, default=0)
    location = db.Column(db.String, nullable=False)
    trainer = db.Column(db.String, nullable=False)

class Relationship(db.Model):
    __tablename__="relations"
    id = db.Column(db.Integer, primary_key=True)
    participant = db.Column(db.Integer, nullable=False)
    classs = db.Column(db.Integer, nullable=False)