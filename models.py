from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50))


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vin = db.Column(db.String(50), unique=True, nullable=False)
    model = db.Column(db.String(100))


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    oem = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    brand = db.Column(db.String(100))
    purchase_price = db.Column(db.Float, default=0.0)
    sell_price = db.Column(db.Float, default=0.0)
    stock = db.Column(db.Integer, default=0)
    # новые поля
    location = db.Column(db.String(100))          # полка / ячейка
    min_stock = db.Column(db.Integer, default=0)  # минимальный остаток
    analogs = db.Column(db.Text)                  # другие OEM-номера через запятую
    note = db.Column(db.Text)

    @property
    def is_low(self):
        return (self.min_stock or 0) > 0 and (self.stock or 0) <= (self.min_stock or 0)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    vin = db.Column(db.String(50))
    comment = db.Column(db.Text)
    status = db.Column(db.String(50))
    total_price = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # новые поля
    payment_method = db.Column(db.String(30))     # Наличные / Терминал / Перевод
    discount = db.Column(db.Float, default=0.0)

    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan")

    @property
    def client_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    oem = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    # новые поля
    product_id = db.Column(db.Integer)
    purchase_price = db.Column(db.Float)          # закуп на момент продажи — для точной прибыли


class StockMovement(db.Model):
    """Журнал движения: приход, продажа, возврат, списание, корректировка."""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, index=True)
    oem = db.Column(db.String(100))
    product_name = db.Column(db.String(200))
    kind = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)  # + пришло, - ушло
    price = db.Column(db.Float, default=0.0)
    supplier = db.Column(db.String(200))
    comment = db.Column(db.Text)
    order_id = db.Column(db.Integer)
    stock_after = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
