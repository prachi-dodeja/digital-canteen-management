from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'canteen-secret-key-2025')

# MongoDB Configuration
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'canteen_db')

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

menu_items_col = db["menu_items"]
orders_col = db["orders"]
order_details_col = db["order_details"]
canteen_status_col = db["canteen_status"]
completed_orders_col = db["completed_orders_archive"]
completed_order_details_col = db["completed_order_details_archive"]

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password123')

def seed_database():
    if canteen_status_col.count_documents({}) == 0:
        print("🔧 Setting up canteen status...")
        canteen_status_col.insert_one({"key": "canteen_open_status", "value": "OPEN"})
    
    if menu_items_col.count_documents({}) == 0:
        print("🍽️ Seeding menu items...")
        menu_items = [
            {"name": "Samosa", "description": "Crispy fried snack with spiced potato filling", "price": 15.00, "preparation_time": 5, "image_url": "samosa.jpg", "category": "Snacks", "is_available": True},
            {"name": "Vada Pav", "description": "Mumbai's favorite street food", "price": 20.00, "preparation_time": 3, "image_url": "vada-pav.png", "category": "Snacks", "is_available": True},
            {"name": "Masala Dosa", "description": "South Indian crispy crepe", "price": 60.00, "preparation_time": 12, "image_url": "masala-dosa.png", "category": "Main Course", "is_available": True},
            {"name": "Chole Bhature", "description": "Spicy chickpea curry with fluffy fried bread", "price": 80.00, "preparation_time": 10, "image_url": "chole-bhature.jpg", "category": "Main Course", "is_available": True},
            {"name": "Filter Coffee", "description": "Traditional South Indian filter coffee", "price": 25.00, "preparation_time": 2, "image_url": "filter-coffee.png", "category": "Beverages", "is_available": True},
            {"name": "Paneer Tikka", "description": "Grilled cottage cheese with spices", "price": 110.00, "preparation_time": 15, "image_url": "paneer-tikka.jpg", "category": "Main Course", "is_available": True},
            {"name": "Pav Bhaji", "description": "Spicy vegetable mash with buttered bread rolls", "price": 70.00, "preparation_time": 8, "image_url": "pav-bhaji.jpg", "category": "Main Course", "is_available": True},
            {"name": "Mango Lassi", "description": "Refreshing yogurt-based mango drink", "price": 50.00, "preparation_time": 4, "image_url": "mango-lassi.jpg", "category": "Beverages", "is_available": True},
            {"name": "Chicken Tikka", "description": "Grilled chicken marinated in Indian spices", "price": 150.00, "preparation_time": 18, "image_url": "chicken-tikka.jpg", "category": "Non-Veg", "is_available": True},
            {"name": "Chicken Burger", "description": "Juicy chicken patty with fresh vegetables", "price": 110.00, "preparation_time": 10, "image_url": "chicken-burger.jpg", "category": "Fast Food", "is_available": True},
            {"name": "Egg Curry", "description": "Boiled eggs in rich spicy gravy", "price": 85.00, "preparation_time": 8, "image_url": "egg-curry.jpg", "category": "Non-Veg", "is_available": True}
        ]
        menu_items_col.insert_many(menu_items)
        print(f"✅ Added {len(menu_items)} menu items")
    print("✅ Database setup complete!")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    menu_items = list(menu_items_col.find({"is_available": True}))
    for item in menu_items:
        item['_id'] = str(item['_id'])
    status = canteen_status_col.find_one({"key": "canteen_open_status"})
    canteen_status = status["value"] if status else "CLOSED"
    return render_template("index.html", menu_items=menu_items, canteen_status=canteen_status)

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        data = request.get_json()
        customer_name = data.get("customer_name", "").strip()
        cart = data.get("cart", [])
        total_price = float(data.get("total_price", 0))
        if not customer_name or not cart:
            return jsonify({"success": False, "message": "Invalid data"}), 400
        prep_times = []
        for item in cart:
            menu_item = menu_items_col.find_one({"_id": ObjectId(item["id"])})
            if menu_item:
                prep_times.append(menu_item.get("preparation_time", 5))
        max_prep_time = max(prep_times) if prep_times else 5
        completion_time = datetime.now() + timedelta(minutes=max_prep_time)
        order = {"customer_name": customer_name, "total_price": total_price, "order_status": "Pending", "order_date": datetime.now(), "estimated_completion_time": completion_time}
        result = orders_col.insert_one(order)
        order_id = str(result.inserted_id)
        for item in cart:
            order_details_col.insert_one({"order_id": order_id, "item_id": item["id"], "item_name": item["name"], "quantity": item["quantity"], "price_per_item": item["price"]})
        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/order_success/<order_id>')
def order_success(order_id):
    try:
        order = orders_col.find_one({"_id": ObjectId(order_id)})
        if not order:
            return "Order not found", 404
        order['_id'] = str(order['_id'])
        items = list(order_details_col.find({"order_id": order_id}))
        return render_template("order_success.html", order=order, order_items=items)
    except:
        return "Error", 500

@app.route('/cancel_order/<order_id>', methods=['POST'])
def cancel_order(order_id):
    try:
        order = orders_col.find_one({"_id": ObjectId(order_id)})
        if not order:
            return jsonify({"success": False}), 404
        if order["order_status"] != "Pending":
            return jsonify({"success": False}), 400
        if (datetime.now() - order["order_date"]).total_seconds() > 10:
            return jsonify({"success": False}), 403
        orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"order_status": "Cancelled"}})
        return jsonify({"success": True})
    except:
        return jsonify({"success": False}), 500

@app.route('/track')
def track_order_page():
    return render_template("track_order.html")

@app.route('/get_order_status/<order_id>')
def get_order_status(order_id):
    try:
        order = orders_col.find_one({"_id": ObjectId(order_id)})
        if order:
            items = list(order_details_col.find({"order_id": order_id}))
            return jsonify({"success": True, "status": order["order_status"], "completion_time": order["estimated_completion_time"].isoformat(), "customer_name": order["customer_name"], "total_price": float(order["total_price"]), "items": [{"name": i["item_name"], "quantity": i["quantity"]} for i in items]})
        return jsonify({"success": False}), 404
    except:
        return jsonify({"success": False}), 500

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template("admin_login.html")

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    orders_col.update_many({"order_status": "Pending", "estimated_completion_time": {"$lte": datetime.now()}}, {"$set": {"order_status": "Completed"}})
    orders = list(orders_col.find().sort("order_date", 1))
    for order in orders:
        order['_id'] = str(order['_id'])
    return render_template("admin_dashboard_ajax.html", orders=orders)

@app.route('/admin/menu')
@login_required
def admin_menu():
    menu_items = list(menu_items_col.find().sort("name", 1))
    for item in menu_items:
        item['_id'] = str(item['_id'])
    return render_template("admin_menu.html", menu_items=menu_items)

@app.route('/admin/menu/add', methods=['POST'])
@login_required
def add_menu_item():
    try:
        menu_items_col.insert_one({"name": request.form["name"], "description": request.form.get("description", ""), "price": float(request.form["price"]), "preparation_time": int(request.form["preparation_time"]), "image_url": request.form.get("image_url", ""), "category": request.form.get("category", "General"), "is_available": True})
        flash('Item added successfully', 'success')
    except:
        flash('Error adding item', 'danger')
    return redirect(url_for('admin_menu'))

@app.route('/admin/menu/edit/<item_id>', methods=['POST'])
@login_required
def edit_menu_item(item_id):
    try:
        menu_items_col.update_one({"_id": ObjectId(item_id)}, {"$set": {"name": request.form["name"], "description": request.form["description"], "price": float(request.form["price"]), "preparation_time": int(request.form["preparation_time"]), "image_url": request.form["image_url"]}})
        flash('Item updated', 'success')
    except:
        flash('Error updating', 'danger')
    return redirect(url_for('admin_menu'))

@app.route('/admin/menu/delete/<item_id>', methods=['POST'])
@login_required
def delete_menu_item(item_id):
    try:
        menu_items_col.delete_one({"_id": ObjectId(item_id)})
        flash('Item deleted', 'success')
    except:
        flash('Error deleting', 'danger')
    return redirect(url_for('admin_menu'))

@app.route('/admin/update_order_status_api', methods=['POST'])
@login_required
def update_order_status_api():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        order = orders_col.find_one({"_id": ObjectId(order_id)})
        if not order:
            return jsonify({"success": False}), 404
        was_late = 1 if order["estimated_completion_time"] < datetime.now() else 0
        completed_orders_col.insert_one({"order_id": order_id, "customer_name": order["customer_name"], "total_price": order["total_price"], "order_date": order["order_date"], "completion_time": datetime.now(), "was_late": was_late})
        items = list(order_details_col.find({"order_id": order_id}))
        for item in items:
            completed_order_details_col.insert_one({"order_id": order_id, "item_name": item["item_name"], "quantity": item["quantity"], "price_per_item": item["price_per_item"]})
        orders_col.delete_one({"_id": ObjectId(order_id)})
        order_details_col.delete_many({"order_id": order_id})
        return jsonify({"success": True})
    except:
        return jsonify({"success": False}), 500

@app.route('/admin/completed_orders')
@login_required
def completed_orders():
    orders = list(completed_orders_col.find().sort("completion_time", -1))
    total_sales = sum(o["total_price"] for o in orders) if orders else 0
    for order in orders:
        order['_id'] = str(order.get('_id', ''))
    return render_template("admin_completed_orders.html", orders=orders, total_sales=total_sales)

@app.route('/admin/api/order_details/<order_id>')
@login_required
def get_order_details_api(order_id):
    try:
        items = list(completed_order_details_col.find({"order_id": order_id}))
        if not items:
            items = list(order_details_col.find({"order_id": order_id}))
        if items:
            return jsonify({"success": True, "items": [{"name": i["item_name"], "quantity": int(i["quantity"]), "price_per_item": float(i["price_per_item"])} for i in items]})
        return jsonify({"success": False}), 404
    except:
        return jsonify({"success": False}), 500

@app.route('/admin/reset_daily_data', methods=['POST'])
@login_required
def reset_daily_data():
    try:
        order_details_col.delete_many({})
        completed_order_details_col.delete_many({})
        orders_col.delete_many({})
        completed_orders_col.delete_many({})
        return jsonify({"success": True})
    except:
        return jsonify({"success": False}), 500

if __name__ == "__main__":
    print("🚀 Starting Canteen Management System...")
    try:
        client.server_info()
        print("✅ MongoDB connected")
    except:
        print("❌ MongoDB connection failed")
        exit(1)
    seed_database()
    print("\n" + "="*60)
    print("🍽️  DIGITAL CANTEEN MANAGEMENT SYSTEM")
    print("="*60)
    print("\n📱 Customer: http://localhost:5000/")
    print("👨‍💼 Admin: http://localhost:5000/admin")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Password: {ADMIN_PASSWORD}\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
```

---

## 📝 FILE 2: `requirements.txt`

**Path**: `requirements.txt`
```
Flask==3.0.0
pymongo==4.6.1
python-dotenv==1.0.0
Werkzeug==3.0.1
```

---

## 📝 FILE 3: `.gitignore`

**Path**: `.gitignore`
```
__pycache__/
*.pyc
*.pyo
*.pyd
venv/
env/
.env
.venv
*.db
*.sqlite3
.DS_Store
.idea/
.vscode/
*.log
