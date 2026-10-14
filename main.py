from flask import Flask, render_template, request, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from models import db, Client, Vehicle, Product

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
auth = HTTPBasicAuth()

# Данные для входа в CRM
USERS = {
    "admin": "zap12345"  # Логин: admin, Пароль: zap12345
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS[username] == password:
        return username

with app.app_context():
    db.create_all()

@app.route('/')
@auth.login_required
def index():
    query = request.args.get('q', '')
    if query:
        products = Product.query.filter(
            (Product.oem.ilike(f'%{query}%')) | 
            (Product.name.ilike(f'%{query}%')) | 
            (Product.brand.ilike(f'%{query}%'))
        ).all()
    else:
        products = Product.query.all()
        
    clients = Client.query.all()
    return render_template('index.html', products=products, clients=clients, query=query)

@app.route('/add_product', methods=['POST'])
@auth.login_required
def add_product():
    oem = request.form.get('oem')
    name = request.form.get('name')
    brand = request.form.get('brand')
    purchase_price = float(request.form.get('purchase_price', 0))
    sell_price = float(request.form.get('sell_price', 0))
    stock = int(request.form.get('stock', 0))
    
    existing = Product.query.filter_by(oem=oem).first()
    if not existing and oem and name:
        new_p = Product(
            oem=oem, 
            name=name, 
            brand=brand, 
            purchase_price=purchase_price, 
            sell_price=sell_price, 
            stock=stock
        )
        db.session.add(new_p)
        db.session.commit()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
