from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    type = db.Column(db.String(20), default='Розница')

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    brand = db.Column(db.String(50))
    model = db.Column(db.String(50))
    year = db.Column(db.Integer)
    vin = db.Column(db.String(17), unique=True)
    gos_number = db.Column(db.String(20))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    oem = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(50))
    purchase_price = db.Column(db.Float, default=0.0)
    sell_price = db.Column(db.Float, default=0.0)
    stock = db.Column(db.Integer, default=0)
    cross_codes = db.Column(db.String(255))

# Таблица заказа (Сделка / Заказ-наряд)
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    vin = db.Column(db.String(50))
    status = db.Column(db.String(50), default='Запрос поступил')
    total_price = db.Column(db.Float, default=0.0)
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')

# Таблица позиций внутри заказа
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    oem = db.Column(db.String(50))
    price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=1)
