import os
import tempfile
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from sqlalchemy import create_engine, text
from models import db, Client, Vehicle, Product, Order, OrderItem

app = Flask(__name__)

# ---------------------------------------------------------------------------
# БАЗА ДАННЫХ
# На Render задайте переменную окружения DATABASE_URL (строка подключения
# к PostgreSQL, например из Neon). Тогда все данные хранятся во внешней базе
# и не пропадают при деплое/перезапуске.
# Без DATABASE_URL (локально) используется файл crm.db, как раньше.
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

USE_POSTGRES = DATABASE_URL.startswith('postgresql')

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL if USE_POSTGRES else 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,   # переподключение, если облачная база "уснула"
    'pool_recycle': 280,
}

db.init_app(app)
auth = HTTPBasicAuth()

# ---------------------------------------------------------------------------
# ВХОД
# Логин и пароль задаются переменными окружения ADMIN_USER и ADMIN_PASSWORD.
# Если они не заданы, работает старый вход admin / zap12345.
# ---------------------------------------------------------------------------
USERS = {
    os.environ.get('ADMIN_USER', 'admin'): os.environ.get('ADMIN_PASSWORD', 'zap12345')
}


@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS[username] == password:
        return username


# ---------------------------------------------------------------------------
# ЯНДЕКС.ДИСК
# Токен теперь берётся только из переменной окружения YANDEX_TOKEN.
# С PostgreSQL он нужен только один раз: чтобы перенести старые данные
# из резервной копии crm_backup.db в новую базу.
# ---------------------------------------------------------------------------
YANDEX_TOKEN = os.environ.get('YANDEX_TOKEN', '').strip()
BACKUP_PATH_ON_DISK = 'app:/crm_backup.db'


def download_yandex_backup(dest_path):
    """Скачивает crm_backup.db с Яндекс.Диска. Возвращает True при успехе."""
    if not YANDEX_TOKEN:
        return False
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        url = f"https://cloud-api.yandex.net/v1/disk/resources/download?path={BACKUP_PATH_ON_DISK}"
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            download_url = response.json().get('href')
            r = requests.get(download_url, timeout=60)
            if r.status_code == 200 and r.content:
                with open(dest_path, 'wb') as f:
                    f.write(r.content)
                return True
    except Exception as e:
        print(f"Ошибка загрузки бэкапа: {e}")
    return False


def backup_to_yandex_disk():
    """Бэкап файла crm.db на Яндекс.Диск (нужен только в режиме SQLite)."""
    if USE_POSTGRES or not YANDEX_TOKEN:
        return
    db_path = os.path.join(app.instance_path, 'crm.db')
    if not os.path.exists(db_path):
        db_path = 'crm.db'
    if os.path.exists(db_path):
        headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
        try:
            url = f"https://cloud-api.yandex.net/v1/disk/resources/upload?path={BACKUP_PATH_ON_DISK}&overwrite=true"
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                upload_url = response.json().get('href')
                with open(db_path, 'rb') as f:
                    requests.put(upload_url, data=f, timeout=60)
        except Exception as e:
            print(f"Ошибка бэкапа: {e}")


def restore_sqlite_from_yandex():
    """Режим SQLite: восстановить crm.db с Яндекс.Диска при старте."""
    if USE_POSTGRES or not YANDEX_TOKEN:
        return
    os.makedirs(app.instance_path, exist_ok=True)
    download_yandex_backup(os.path.join(app.instance_path, 'crm.db'))


# Порядок важен: сначала таблицы без внешних ключей
MODELS_IN_ORDER = [Client, Vehicle, Product, Order, OrderItem]


def import_from_sqlite_file(sqlite_path):
    """Переносит все данные из файла SQLite в текущую базу (PostgreSQL)."""
    src_engine = create_engine(f'sqlite:///{sqlite_path}')
    total = 0
    try:
        with src_engine.connect() as src:
            existing_tables = {
                row[0] for row in src.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            }
            for model in MODELS_IN_ORDER:
                table = model.__table__
                if table.name not in existing_tables:
                    continue
                rows = [dict(r._mapping) for r in src.execute(table.select())]
                if rows:
                    db.session.execute(table.insert(), rows)
                    total += len(rows)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка переноса данных: {e}")
        return 0
    finally:
        src_engine.dispose()

    # Чтобы новые записи получали правильные id после переноса
    if USE_POSTGRES:
        for model in MODELS_IN_ORDER:
            t = model.__table__.name
            db.session.execute(text(
                f"SELECT setval(pg_get_serial_sequence('\"{t}\"', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{t}\"), 0) + 1, false)"
            ))
        db.session.commit()
    return total


def migrate_old_data_if_needed():
    """Один раз: если PostgreSQL пустая, забираем старые данные с Яндекс.Диска."""
    if not USE_POSTGRES or not YANDEX_TOKEN:
        return
    if Product.query.first() or Order.query.first():
        return  # в базе уже есть данные — ничего не трогаем
    tmp_path = os.path.join(tempfile.gettempdir(), 'crm_backup_import.db')
    if download_yandex_backup(tmp_path):
        count = import_from_sqlite_file(tmp_path)
        print(f"Перенесено записей из старой базы: {count}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass


with app.app_context():
    restore_sqlite_from_yandex()
    db.create_all()
    migrate_old_data_if_needed()


@app.route('/')
@auth.login_required
def index():
    backup_to_yandex_disk()
    all_products = Product.query.all()

    selected_month = request.args.get('month', '')
    try:
        orders_query = Order.query
        if selected_month:
            year, month = selected_month.split('-')
            orders_query = orders_query.filter(
                db.extract('year', Order.created_at) == int(year),
                db.extract('month', Order.created_at) == int(month)
            )
        orders = orders_query.all()
    except Exception:
        db.session.rollback()
        orders = Order.query.all()

    stock_value_cost = sum((p.purchase_price or 0) * (p.stock or 0) for p in all_products)
    stock_value_sell = sum((p.sell_price or 0) * (p.stock or 0) for p in all_products)

    total_sales = sum(o.total_price or 0 for o in orders)

    purchase_by_oem = {p.oem: (p.purchase_price or 0) for p in all_products}
    total_cost_sold = 0.0
    for o in orders:
        for item in o.items:
            total_cost_sold += purchase_by_oem.get(item.oem, 0.0) * item.quantity

    total_profit = total_sales - total_cost_sold

    analytics = {
        "stock_cost": round(stock_value_cost, 2),
        "stock_sell": round(stock_value_sell, 2),
        "total_sales": round(total_sales, 2),
        "total_profit": round(total_profit, 2)
    }

    return render_template('index.html', products=all_products, analytics=analytics, selected_month=selected_month)


@app.route('/products')
@auth.login_required
def products_page():
    query = request.args.get('q', '')
    if query:
        products = Product.query.filter(
            (Product.oem.ilike(f'%{query}%')) |
            (Product.name.ilike(f'%{query}%')) |
            (Product.brand.ilike(f'%{query}%'))
        ).all()
    else:
        products = Product.query.all()
    return render_template('products.html', products=products, query=query)


@app.route('/orders')
@auth.login_required
def orders_page():
    orders = Order.query.order_by(Order.id.desc()).all()
    return render_template('orders.html', orders=orders)


@app.route('/manual_backup', methods=['POST'])
@auth.login_required
def manual_backup():
    backup_to_yandex_disk()
    return redirect(url_for('index'))


@app.route('/add_product', methods=['POST'])
@auth.login_required
def add_product():
    oem = (request.form.get('oem') or '').strip()
    name = (request.form.get('name') or '').strip()
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
    return redirect(url_for('products_page'))


@app.route('/delete_product/<int:id>', methods=['POST'])
@auth.login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('products_page'))


@app.route('/edit_product/<int:id>', methods=['POST'])
@auth.login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    product.name = request.form.get('name', product.name)
    product.brand = request.form.get('brand', product.brand)
    product.sell_price = float(request.form.get('sell_price') or product.sell_price)
    product.stock = int(request.form.get('stock') or product.stock)
    db.session.commit()
    return redirect(url_for('products_page'))


@app.route('/create_order', methods=['POST'])
@auth.login_required
def create_order():
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone')
    vin = request.form.get('vin')
    comment = request.form.get('comment')
    status = request.form.get('status')

    product_ids = request.form.getlist('product_ids')
    quantities = request.form.getlist('quantities')

    if not first_name or not phone:
        return redirect(url_for('index'))

    new_order = Order(
        first_name=first_name,
        last_name=last_name or '',
        phone=phone,
        vin=vin,
        comment=comment,
        status=status,
        total_price=0.0
    )
    db.session.add(new_order)
    db.session.flush()  # получаем id заказа без отдельного сохранения

    total = 0.0
    for p_id, qty_str in zip(product_ids, quantities):
        try:
            qty = int(qty_str)
            if qty > 0:
                product = db.session.get(Product, int(p_id))
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
    db.session.commit()  # заказ, позиции и остатки сохраняются вместе
    return redirect(url_for('orders_page'))


@app.route('/delete_order/<int:id>', methods=['POST'])
@auth.login_required
def delete_order(id):
    order = Order.query.get_or_404(id)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for('orders_page'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
