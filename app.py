from flask import Flask, render_template, request, redirect, url_for, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secretkey"
app.config["MONGO_URI"] = "mongodb+srv://user:user@cluster0.u3fdtma.mongodb.net/md3"
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
mongo = PyMongo(app)

# ------------------ AUTH ------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if mongo.db.users.find_one({"email": email}):
            return "User already exists!"
        hashed = generate_password_hash(password)
        mongo.db.users.insert_one({"email": email, "password": hashed})
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = mongo.db.users.find_one({"email": email})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["email"] = str(user["email"])
            return redirect(url_for("dashboard"))
        return "Invalid credentials!"
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------ DASHBOARD ------------------

@app.route("/")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("landing"))

    user = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})
    user_email = user.get("email")
    # Get orgs where user is owner or listed in users
    orgs = list(mongo.db.organizations.find({
        "$or": [
            {"user_id": session["user_id"]},
            {"users": user_email}
        ]
    }))
    return render_template("dashboard.html", orgs=orgs)


@app.route("/add_org", methods=["GET", "POST"])
def add_org():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        users = request.form.get("users", "")
        category = request.form.get("category", "")
        mongo.db.organizations.insert_one({
            "user_id": session["user_id"],  # owner
            "name": name,
            "users": [email.strip() for email in users.split(",") if email.strip()],
            "category": [cat.strip() for cat in category.split(",") if cat.strip()]
        })
        return redirect(url_for("dashboard"))
    return render_template("new_org.html")


@app.route("/<org_id>/edit_org", methods=["GET", "POST"])
def edit_org(org_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org:
        return "Organization not found", 404

    if request.method == "POST":
        name = request.form["name"]
        users = request.form.get("users", "") 
        category = request.form.get("category", "")
        mongo.db.organizations.update_one(
            {"_id": ObjectId(org_id)},
            {"$set": {
                "name": name,
                "users": [email.strip() for email in users.split(",") if email.strip()],
                "category": [cat.strip() for cat in category.split(",") if cat.strip()]
            }}
        )
        return redirect(url_for("dashboard"))

    return render_template("new_org.html", org=org)

# ------------------ ORGANIZATION & PAGES ------------------

def has_org_access(org):
    user = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})
    user_email = user.get("email")
    return user_email in org.get("users", []) or org["user_id"] == session["user_id"]

# ------------------ PAGE ID COUNTER ------------------

def get_next_page_id(org_id):
    counter = mongo.db.counters.find_one_and_update(
        {"org_id": org_id},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    return counter["seq"]

# ------------------ ORG PAGES ------------------

@app.route("/<org_id>")
def org_pages(org_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Fetch org
    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403

    # Read search params
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    # Build search filter
    search_filter = {"org_id": org_id}

    if query:
        search_filter["$text"] = {"$search": query}

    if category:
        search_filter["category"] = category

    # Fetch pages (filtered if query or category is given)
    pages = list(mongo.db.pages.find(search_filter).sort("page_id", 1))

    return render_template(
        "org_pages.html",       # your org home template
        org=org,
        pages=pages,
        query=query,
        category=category,
        searching=bool(query or category)
    )

@app.route("/<org_id>/new", methods=["GET", "POST"])
def new_page(org_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403

    if request.method == "POST":
        page_id = get_next_page_id(org_id)  # incremental page ID

        page_data = {
            "org_id": org_id,
            "page_id": page_id,
            "title": request.form["title"],
            "subtitle": request.form.get("subtitle"),
            "content": request.form["content"],
            "author": session.get("email"),
            "category": request.form.get("category"),
            "tags": request.form.get("tags"),
            "status": request.form.get("status", "pending"),
            "bgimg": request.form.get("bgimg"),
            "created_at": datetime.utcnow()
        }
        mongo.db.pages.insert_one(page_data)
        return redirect(url_for("org_pages", org_id=org_id))

    return render_template("new_page.html", org_id=org_id,org=org)

@app.route("/<org_id>/page/<int:page_id>/edit", methods=["GET", "POST"])
def edit_page(org_id, page_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    page = mongo.db.pages.find_one({"org_id": org_id, "page_id": page_id})
    if not page:
        return "Page not found", 404
    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403
    if request.method == "POST":
        mongo.db.pages.update_one(
            {"org_id": org_id, "page_id": page_id},
            {"$set": {
                "title": request.form["title"],
                "subtitle": request.form.get("subtitle"),
                "content": request.form["content"],
                "category": request.form.get("category"),
                "tags": request.form.get("tags"),
                "status": request.form.get("status", "pending"),
                "bgimg": request.form.get("bgimg"),
                "updated_at": datetime.utcnow()
            }}
        )
        return redirect(url_for("view_page", org_id=org_id, page_id=page_id))

    return render_template("new_page.html", page=page, org_id=org_id,org=org)


@app.route("/<org_id>/page/<int:page_id>")
def view_page(org_id, page_id):
    page = mongo.db.pages.find_one({"org_id": org_id, "page_id": page_id})

    if not page:
        return "Page not found", 404


    if "user_id" not in session:
        return redirect(url_for("login"))

    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403

    timestamp = page.get("created_at", datetime.utcnow())

    data = {
        "title": page.get("title"),
        "headline": page.get("subtitle"),
        "content": page.get("content"),
        "page_id":page.get("page_id"),
        "author": page.get("author") or "Unknown",
        "timestamp": timestamp,
        "bgimg": page.get("bgimg") or url_for('static', filename='assets/img/post-bg.jpg'),
        "category": page.get("category") or "",
        "tags": page.get("tags") or "",
        "status": page.get("status") or "pending",
    }

    return render_template("view_page.html", data=data, org=org)


# ------------------ SEARCH ------------------


@app.route("/landing")
def landing():
    return render_template("landing.html")


if __name__ == "__main__":
    # Ensure text index exists for search
    app.run(debug=True)
