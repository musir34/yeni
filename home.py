from flask import Blueprint, render_template

home_bp = Blueprint("home", __name__)

@home_bp.route("/", endpoint="home")
@home_bp.route("/home", endpoint="home")
@home_bp.route("/anasayfa", endpoint="home")
def index():
    stats = {"toplam_siparis": 0, "hazirlanan": 0, "iade": 0, "kritik_stok": 0}
    return render_template("home.html", stats=stats)
