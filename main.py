import os
import requests
from flask import Flask, render_template, request, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from models import db, Client, Vehicle, Product

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
auth = HTTPBasicAuth()

USERS = {
    "admin": "zap12345"  # Логин и пароль для входа в CRM
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS[username] == password:
        return username

# Ваш OAuth-токен Яндекс.Диска
YANDEX_TOKEN = "y0__wgBEJKG960HGJW0SyDKzqioGbuBt_HQl-9a_ugEH5cUuWmZV5h5" 

def backup_to_yandex_disk():
    if not YANDEX_TOKEN:
        return
    
    db_path = 'crm.db'
    if os.path.exists(db_path):
        headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
        try:
            url = "https://cloud-api.yandex.net/v1/disk/resources/upload?path=app:/crm_backup.db&overwrite=true"
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                upload_url = response.json().get('href')
                with open(db_path, 'rb') as f:
                    requests.put(upload_url, files={'file': f})
        except Exception as e:
            print(f"Ошибка бэкапа: {e}")

with app.app_context():
    db.create_all()

@app.route('/')
@auth.login_required
def index():
    backup_to_yandex_disk()
    
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

# Удаление товара
@app.route('/delete_product/<int:id>', methods=['POST'])
@auth.login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('index'))

# Изменение количества или данных товара
@app.route('/edit_product/<int:id>', methods=['POST'])
@auth.login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    product.name = request.form.get('name', product.name)
    product.brand = request.form.get('brand', product.brand)
    product.sell_price = float(request.form.get('sell_price', product.sell_price))
    product.stock = int(request.form.get('stock', product.stock))
    
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
