from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    has_temporary_password = db.Column(db.Boolean, default=False, nullable=False)


class Cellar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cellar_type = db.Column(db.String(50), nullable=False)
    floors = db.Column(db.Integer, nullable=False)
    bottles_per_floor = db.Column(db.Integer, nullable=False)

    wines = db.relationship("Wine", back_populates="cellar", lazy="dynamic")

    @property
    def capacity(self):
        return self.floors * self.bottles_per_floor


class Wine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    region = db.Column(db.String(120))
    grape = db.Column(db.String(80))
    year = db.Column(db.Integer)
    barcode = db.Column(db.String(20), unique=True)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    quantity = db.Column(db.Integer, default=1)
    cellar_id = db.Column(db.Integer, db.ForeignKey("cellar.id"), nullable=False)

    cellar = db.relationship("Cellar", back_populates="wines")
