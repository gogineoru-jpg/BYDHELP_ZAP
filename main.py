from flask import Flask, render_template, request, redirect, url_for
from models import db, Client, Vehicle, Product

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    products = Product.query.all()
    clients = Client.query.all()
    return render_template('index.html', products=products, clients=clients)

@app.route('/add_product', methods=['POST'])
def add_product():
    oem = request.form.get('oem')
    name = request.form.get('name')
    brand = request.form.get('brand')
    sell_price = float(request.form.get('sell_price', 0))
    stock = int(request.form.get('stock', 0))
    
    new_p = Product(oem=oem, name=name, brand=brand, sell_price=sell_price, stock=stock)
    db.session.add(new_p)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
