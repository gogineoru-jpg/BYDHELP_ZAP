import os
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from models import db, Client, Vehicle, Product, Order, OrderItem

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
auth = HTTPBasicAuth()

USERS = {
    "admin": "zap12345"
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS[username] == password:
        return username

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
        
    all_products = Product.query.all()
    
    # Фильтр заказов по выбранному месяцу (календарь)
    selected_month = request.args.get('month', '')
    orders_query = Order.query
    
    if selected_month:
        try:
            year, month = selected_month.split('-')
            orders_query = orders_query.filter(
                db.extract('year', Order.created_at) == int(year),
                db.extract('month', Order.created_at) == int(month)
            )
        except Exception:
            pass
            
    orders = orders_query.order_by(Order.id.desc()).all()

    # Аналитика склада (всегда по всему складу)
    stock_value_cost = sum(p.purchase_price * p.stock for p in all_products)
    stock_value_sell = sum(p.sell_price * p.stock for p in all_products)
    
    # Аналитика продаж за выбранный период
    total_sales = sum(o.total_price for o in orders)
    
    total_cost_sold = 0.0
    for o in orders:
        for item in o.items:
            prod = Product.query.filter_by(oem=item.oem).first()
            p_price = prod.purchase_price if prod else 0.0
            total_cost_sold += p_price * item.quantity

    total_profit = total_sales - total_cost_sold

    analytics = {
        "stock_cost": round(stock_value_cost, 2),
        "stock_sell": round(stock_value_sell, 2),
        "total_sales": round(total_sales, 2),
        "total_profit": round(total_profit, 2)
    }

    return render_template('index.html', products=products, orders=orders, query=query, analytics=analytics, selected_month=selected_month)

@app.route('/manual_backup', methods=['POST'])
@auth.login_required
def manual_backup():
    backup_to_yandex_disk()
    return redirect(url_for('index'))

@app.route('/add_product', methods=['POST'])
@auth.login_required
def add_product():
    oem = request.form.get('oem')
    name = request.form.get('name')
    brand = request.form.get('brand')
    purchase_price = float(request.form.get('purchase_price') or 0)
    sell_price = float(request.form.get('sell_price') or 0)
    stock = int(request.form.get('stock') or 1)
    
    existing = Product.query.filter_by(oem=oem).first()
    if not existing and oem and name:
        new_p = Product(
            oem=oem, name=name, brand=brand, 
            purchase_price=purchase_price, sell_price=sell_price, stock=stock
        )
        db.session.add(new_p)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_product/<int:id>', methods=['POST'])
@auth.login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/edit_product/<int:id>', methods=['POST'])
@auth.login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    product.name = request.form.get('name', product.name)
    product.brand = request.form.get('brand', product.brand)
    product.sell_price = float(request.form.get('sell_price') or product.sell_price)
    product.stock = int(request.form.get('stock') or product.stock)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/create_order', methods=['POST'])
@auth.login_required
def create_order():
    client_name = request.form.get('client_name')
    vin = request.form.get('vin')
    status = request.form.get('status')
    
    product_ids = request.form.getlist('product_ids')
    quantities = request.form.getlist('quantities')
    
    if not client_name or not product_ids:
        return redirect(url_for('index'))
        
    new_order = Order(client_name=client_name, vin=vin, status=status, total_price=0.0)
    db.session.add(new_order)
    db.session.commit()
    
    total = 0.0
    for p_id, qty_str in zip(product_ids, quantities):
        try:
            qty = int(qty_str)
            if qty > 0:
                product = Product.query.get(int(p_id))
                if product:
                    item_sum = product.sell_price * qty
                    total += item_sum
                    
                    order_item = OrderItem(
                        order_id=new_order.id,
                        product_name=product.name,
                        oem=product.oem,
                        price=product.sell_price,
                        quantity=qty
                    )
                    db.session.add(order_item)
                    
                    if product.stock >= qty:
                        product.stock -= qty
        except ValueError:
            continue
            
    new_order.total_price = total
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_order/<int:id>', methods=['POST'])
@auth.login_required
def delete_order(id):
    order = Order.query.get_or_404(id)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
