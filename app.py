from flask import Flask, render_template, request, redirect, url_for, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secretkey"
app.config["MONGO_URI"] = "mongodb+srv://user:user@cluster0.u3fdtma.mongodb.net/md3"
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
mongo = PyMongo(app)

# ------------------ AUTH ------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if mongo.db.users.find_one({"email": email}):
            return render_template("register.html", error="An account with that email already exists.")
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
        return render_template("login.html", error="Invalid email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------ HELPERS ------------------

def has_org_access(org):
    user = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})
    user_email = user.get("email")
    return user_email in org.get("users", []) or org["user_id"] == session["user_id"]


def get_next_page_id(org_id):
    counter = mongo.db.counters.find_one_and_update(
        {"org_id": org_id},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    return counter["seq"]

# ------------------ DASHBOARD ------------------

@app.route("/")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("landing"))

    user = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})
    user_email = user.get("email")
    orgs = list(mongo.db.organizations.find({
        "$or": [
            {"user_id": session["user_id"]},
            {"users": user_email}
        ]
    }))

    # Attach page count to each org
    for org in orgs:
        org["page_count"] = mongo.db.pages.count_documents({"org_id": str(org["_id"])})

    # Recently touched pages across all accessible spaces
    org_ids = [str(o["_id"]) for o in orgs]
    org_map  = {str(o["_id"]): o for o in orgs}
    recent_pages = []
    if org_ids:
        raw = list(
            mongo.db.pages.find({"org_id": {"$in": org_ids}})
            .sort("created_at", -1)
            .limit(50)
        )
        raw.sort(
            key=lambda p: p.get("updated_at") or p.get("created_at") or datetime.min,
            reverse=True
        )
        recent_pages = raw[:8]
        for p in recent_pages:
            p["org"] = org_map.get(p["org_id"])

    return render_template("dashboard.html", orgs=orgs, recent_pages=recent_pages)


@app.route("/add_org", methods=["GET", "POST"])
def add_org():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        users = request.form.get("users", "")
        category = request.form.get("category", "")
        mongo.db.organizations.insert_one({
            "user_id": session["user_id"],
            "name": name,
            "users": [e.strip() for e in users.split(",") if e.strip()],
            "category": [c.strip() for c in category.split(",") if c.strip()]
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
    if org["user_id"] != session["user_id"]:
        return "Only the space owner can edit settings.", 403

    if request.method == "POST":
        name = request.form["name"]
        users = request.form.get("users", "")
        category = request.form.get("category", "")
        mongo.db.organizations.update_one(
            {"_id": ObjectId(org_id)},
            {"$set": {
                "name": name,
                "users": [e.strip() for e in users.split(",") if e.strip()],
                "category": [c.strip() for c in category.split(",") if c.strip()]
            }}
        )
        return redirect(url_for("org_pages", org_id=org_id))

    return render_template("new_org.html", org=org)


@app.route("/<org_id>/delete_org", methods=["POST"])
def delete_org(org_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or org["user_id"] != session["user_id"]:
        return "Only the space owner can delete this space.", 403
    mongo.db.pages.delete_many({"org_id": org_id})
    mongo.db.counters.delete_one({"org_id": org_id})
    mongo.db.organizations.delete_one({"_id": ObjectId(org_id)})
    return redirect(url_for("dashboard"))

# ------------------ ORG PAGES ------------------

@app.route("/<org_id>")
def org_pages(org_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403

    query    = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    search_filter = {"org_id": org_id}
    if query:
        search_filter["$text"] = {"$search": query}
    if category:
        search_filter["category"] = category

    pages = list(mongo.db.pages.find(search_filter).sort("page_id", 1))

    return render_template(
        "org_pages.html",
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
        page_id = get_next_page_id(org_id)
        mongo.db.pages.insert_one({
            "org_id":     org_id,
            "page_id":    page_id,
            "title":      request.form["title"],
            "subtitle":   request.form.get("subtitle"),
            "content":    request.form["content"],
            "author":     session.get("email"),
            "category":   request.form.get("category"),
            "tags":       request.form.get("tags"),
            "status":     request.form.get("status", "pending"),
            "bgimg":      request.form.get("bgimg"),
            "created_at": datetime.utcnow()
        })
        return redirect(url_for("org_pages", org_id=org_id))

    return render_template("new_page.html", org_id=org_id, org=org)


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
                "title":      request.form["title"],
                "subtitle":   request.form.get("subtitle"),
                "content":    request.form["content"],
                "category":   request.form.get("category"),
                "tags":       request.form.get("tags"),
                "status":     request.form.get("status", "pending"),
                "bgimg":      request.form.get("bgimg"),
                "updated_at": datetime.utcnow(),
                "updated_by": session.get("email"),
            }}
        )
        return redirect(url_for("view_page", org_id=org_id, page_id=page_id))

    return render_template("new_page.html", page=page, org_id=org_id, org=org)


@app.route("/<org_id>/page/<int:page_id>")
def view_page(org_id, page_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    page = mongo.db.pages.find_one({"org_id": org_id, "page_id": page_id})
    if not page:
        return "Page not found", 404

    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403

    # Lightweight page list for sidebar tree
    all_pages = list(
        mongo.db.pages.find(
            {"org_id": org_id},
            {"page_id": 1, "title": 1, "status": 1}
        ).sort("page_id", 1)
    )

    data = {
        "title":      page.get("title"),
        "headline":   page.get("subtitle"),
        "content":    page.get("content"),
        "page_id":    page.get("page_id"),
        "author":     page.get("author") or "Unknown",
        "timestamp":  page.get("created_at", datetime.utcnow()),
        "updated_at": page.get("updated_at"),
        "updated_by": page.get("updated_by"),
        "category":   page.get("category") or "",
        "tags":       page.get("tags") or "",
        "status":     page.get("status") or "pending",
    }

    return render_template("view_page.html", data=data, org=org, all_pages=all_pages)


@app.route("/<org_id>/page/<int:page_id>/delete", methods=["POST"])
def delete_page(org_id, page_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    org = mongo.db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org or not has_org_access(org):
        return "Access denied", 403
    mongo.db.pages.delete_one({"org_id": org_id, "page_id": page_id})
    return redirect(url_for("org_pages", org_id=org_id))


@app.route("/landing")
def landing():
    return render_template("landing.html")


if __name__ == "__main__":
    app.run(debug=True)
